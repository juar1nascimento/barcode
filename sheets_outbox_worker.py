"""Worker idempotente para sincronizar fotos do Supabase com Google Sheets.

Uso em CI/cron:
  DATABASE_URL=... GOOGLE_SERVICE_ACCOUNT_JSON=... \
  GOOGLE_SPREADSHEET_ID=... SUPABASE_URL=... \
  python sheets_outbox_worker.py
"""
from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import quote, urljoin, urlparse, parse_qs
import base64
import requests
from datetime import datetime, timezone

import gspread
import psycopg
from google.oauth2.service_account import Credentials


PHOTO_COLUMNS = [f"Foto {i}" for i in range(1, 11)]
ID_COLUMN = "ID Patrimônio"
BUCKET = "patrimonio-fotos"
PHOTO_THUMBNAIL_SIZE = 96
PHOTO_URL_EXPIRATION_SECONDS = 86_400
PHOTO_URL_REFRESH_THRESHOLD_SECONDS = 7_200
SHEETS_RENEWAL_MAX_ROWS = max(1, int(os.getenv("SHEETS_RENEWAL_MAX_ROWS", "5000")))


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value


def database_url() -> str:
    value = env("DATABASE_URL")
    if value.upper() == "URL" or "://" not in value:
        raise RuntimeError(
            "GTI_DATABASE_URL inválida: o secret deve conter a connection string "
            "PostgreSQL completa (postgresql://...). O valor configurado não é "
            "uma URL de conexão válida."
        )
    return value


def col_letter(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def sheet_url(storage_path: str) -> str:
    base = env("SUPABASE_URL").rstrip("/")
    key = env("SUPABASE_SERVICE_ROLE_KEY")
    path = str(storage_path or "").lstrip("/")
    if not path:
        raise RuntimeError("Caminho da foto vazio.")
    endpoint = f"{base}/storage/v1/object/sign/{quote(BUCKET)}/{quote(path, safe='/')}"
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": "application/json"},
        json={"expiresIn": PHOTO_URL_EXPIRATION_SECONDS},
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError(f"Falha ao gerar URL temporária da foto (HTTP {response.status_code}).")
    payload = response.json()
    signed = payload.get("signedURL") or payload.get("signedUrl")
    if not signed:
        raise RuntimeError("Supabase não retornou URL temporária da foto.")
    return urljoin(f"{base}/", str(signed).lstrip("/"))


def _signed_url_expiry(url: str) -> int | None:
    """Extrai expiração de tokens JWT usados por URLs assinadas do Storage."""
    try:
        token = parse_qs(urlparse(url).query).get("token", [""])[0]
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return int(data.get("exp"))
    except (ValueError, TypeError, KeyError, IndexError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _photo_formula(url: str) -> str:
    escaped = url.replace('"', '""')
    return (
        f'=HYPERLINK("{escaped}",'
        f'IMAGE("{escaped}",4,{PHOTO_THUMBNAIL_SIZE},{PHOTO_THUMBNAIL_SIZE}))'
    )


def _photo_path_from_url(url: str) -> str | None:
    marker = "/storage/v1/object/sign/"
    object_part = urlparse(url).path.split(marker, 1)[-1]
    prefix = f"{BUCKET}/"
    if not object_part.startswith(prefix):
        return None
    return object_part[len(prefix):]


def _url_from_formula(formula: str) -> str | None:
    match = re.search(r'HYPERLINK\("((?:[^"]|"")+)"', str(formula or ""))
    return match.group(1).replace('""', '"') if match else None


def renew_expiring_sheet_photo_urls(sheets, max_rows: int = SHEETS_RENEWAL_MAX_ROWS) -> dict:
    """Renova URLs próximas da expiração sem alterar a imagem exibida na célula."""
    spreadsheet = open_spreadsheet(sheets)
    renewed = scanned = errors = 0
    now = int(time.time())

    for aba in spreadsheet.worksheets():
        values = aba.get_all_values(value_render_option="FORMULA")
        if not values:
            continue
        header = list(values[0])
        photo_indexes = [header.index(col) for col in PHOTO_COLUMNS if col in header]
        if not photo_indexes:
            continue

        for row_idx, row in enumerate(values[1:max_rows + 1], start=2):
            for col_idx in photo_indexes:
                if col_idx >= len(row):
                    continue
                current = str(row[col_idx] or "").strip()
                url = _url_from_formula(current)
                if not url:
                    continue
                scanned += 1
                exp = _signed_url_expiry(url)
                if exp is not None and exp - now > PHOTO_URL_REFRESH_THRESHOLD_SECONDS:
                    continue
                path = _photo_path_from_url(url)
                if not path:
                    errors += 1
                    continue
                try:
                    new_url = sheet_url(path)
                    aba.update(
                        values=[[_photo_formula(new_url)]],
                        range_name=f"{col_letter(col_idx + 1)}{row_idx}",
                        value_input_option="USER_ENTERED",
                    )
                    renewed += 1
                except Exception:
                    errors += 1

    return {"scanned": scanned, "renewed": renewed, "errors": errors}


def normalize_unit(value: str) -> str:
    aliases = {"URS Jacara_pe": "URS Jacaraípe", "UBS Bairro de F_tima": "UBS Bairro de Fátima"}
    return aliases.get(str(value or "").strip(), str(value or "").strip())


def sheets_client():
    raw = env("GOOGLE_SERVICE_ACCOUNT_JSON")
    data = json.loads(raw)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    return gspread.authorize(Credentials.from_service_account_info(data, scopes=scopes))


def _safe_error(error: Exception | str) -> str:
    """Remove credenciais e URLs potencialmente sensíveis dos logs."""
    value = str(error or "")
    value = re.sub(r"(?i)(postgres(?:ql)?://)[^\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(token=)[^&\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", "[REDACTED PEM]", value, flags=re.DOTALL)
    return value[:500]


def open_spreadsheet(client):
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "").strip()
    spreadsheet_url = os.getenv("GOOGLE_SPREADSHEET_URL", "").strip()
    if spreadsheet_id:
        return client.open_by_key(spreadsheet_id)
    if spreadsheet_url:
        return client.open_by_url(spreadsheet_url)
    raise RuntimeError("Defina GOOGLE_SPREADSHEET_ID ou GOOGLE_SPREADSHEET_URL.")


def claim_batch(conn, limit: int):
    with conn.cursor() as cur:
        cur.execute(
            """WITH candidatos AS (
                 SELECT id
                   FROM public.patrimonio_fotos_sheets_outbox
                  WHERE status IN ('pending','failed')
                    AND proxima_tentativa_em <= now()
                  ORDER BY id
                  FOR UPDATE SKIP LOCKED
                  LIMIT %s
               )
               UPDATE public.patrimonio_fotos_sheets_outbox o
                  SET status = 'processing',
                      processando_em = now(),
                      tentativas = tentativas + 1,
                      atualizado_em = now()
                 FROM candidatos c
                WHERE o.id = c.id
               RETURNING o.id, o.patrimonio_id, o.foto_id""",
            (limit,),
        )
        rows = cur.fetchall()
    conn.commit()
    return rows


def mark(conn, outbox_id: int, status: str, error: str | None = None, max_attempts: int = 8):
    with conn.cursor() as cur:
        if status == "synced":
            cur.execute(
                """UPDATE public.patrimonio_fotos_sheets_outbox
                      SET status='synced', sincronizado_em=now(),
                          processando_em=NULL, ultimo_erro=NULL,
                          atualizado_em=now()
                    WHERE id=%s""",
                (outbox_id,),
            )
        else:
            cur.execute(
                """UPDATE public.patrimonio_fotos_sheets_outbox
                      SET status=CASE WHEN tentativas >= %s THEN 'dead_letter' ELSE 'failed' END,
                          processando_em=NULL,
                          proxima_tentativa_em=CASE
                            WHEN tentativas >= %s THEN now()
                            ELSE now() + LEAST(interval '1 hour',
                                  interval '5 minutes' * power(2, tentativas - 1))
                          END,
                          ultimo_erro=%s,
                          atualizado_em=now()
                    WHERE id=%s""",
                (max_attempts, max_attempts, str(error or "erro")[:2000], outbox_id),
            )
    conn.commit()


def reset_stale(conn):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE public.patrimonio_fotos_sheets_outbox
                  SET status='failed', processando_em=NULL,
                      proxima_tentativa_em=now(),
                      ultimo_erro='job recuperado após expiração do lock',
                      atualizado_em=now()
                WHERE status='processing'
                  AND processando_em IS NOT NULL
                  AND processando_em < now() - interval '15 minutes'"""
        )
    conn.commit()


def sync_one(conn, sheets, outbox_id: int, patrimonio_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.id, p.numero_patrimonio, u.nome
                 FROM public.patrimonios p
                 JOIN public.unidades u ON u.id=p.unidade_id
                WHERE p.id=%s""",
            (patrimonio_id,),
        )
        patrimonio = cur.fetchone()
        cur.execute(
            """SELECT ordem, storage_path
                 FROM public.patrimonio_fotos
                WHERE patrimonio_id=%s
                ORDER BY ordem, id""",
            (patrimonio_id,),
        )
        fotos = cur.fetchall()

    if not patrimonio:
        raise RuntimeError(f"Patrimônio {patrimonio_id} não encontrado.")

    _, numero, unidade = patrimonio
    aba = sheets.worksheet(normalize_unit(unidade))
    values = aba.get_all_values()
    if not values:
        raise RuntimeError(f"Aba {unidade} sem cabeçalho.")

    header = list(values[0])
    while header and header[-1] == "":
        header.pop()

    changed = False
    if ID_COLUMN not in header:
        header.append(ID_COLUMN)
        changed = True
    for col in PHOTO_COLUMNS:
        if col not in header:
            header.append(col)
            changed = True

    if changed:
        aba.update(
            values=[header],
            range_name=f"A1:{col_letter(len(header))}1",
        )
        values = aba.get_all_values()

    id_idx = header.index(ID_COLUMN)
    number_idx = header.index("Nº de Patrimônio") if "Nº de Patrimônio" in header else 2
    row_number = None
    for row_idx, row in enumerate(values[1:], start=2):
        stable_id = row[id_idx].strip() if len(row) > id_idx else ""
        number = row[number_idx].strip() if len(row) > number_idx else ""
        if stable_id == str(patrimonio_id) or (
            not stable_id and re.sub(r"\s+", " ", number).casefold()
            == re.sub(r"\s+", " ", str(numero)).casefold()
        ):
            row_number = row_idx
            break

    if row_number is None:
        raise RuntimeError(f"Patrimônio {numero} não encontrado na aba {unidade}.")

    aba.update(
        values=[[str(patrimonio_id)]],
        range_name=f"{col_letter(id_idx + 1)}{row_number}",
    )

    formulas = [_photo_formula(sheet_url(path)) for _, path in fotos[:10]]
    formulas += [""] * (10 - len(formulas))
    first = header.index(PHOTO_COLUMNS[0]) + 1
    last = first + 9
    target_range = f"{col_letter(first)}{row_number}:{col_letter(last)}{row_number}"
    aba.update(
        values=[formulas],
        range_name=target_range,
        value_input_option="USER_ENTERED",
    )

    # Confirmação pós-escrita: só concluímos o evento quando o destino
    # devolve as mesmas fórmulas esperadas. Isso torna o processamento
    # idempotente e evita marcar como synced uma escrita não confirmada.
    confirmed = aba.get(target_range, value_render_option="FORMULA")
    actual = confirmed[0] if confirmed else []
    actual = list(actual) + [""] * (10 - len(actual))
    expected = list(formulas)
    if actual[:10] != expected[:10]:
        raise RuntimeError(
            f"Google Sheets não confirmou as fórmulas do patrimônio {patrimonio_id}."
        )


def main():
    limit = max(1, int(os.getenv("OUTBOX_BATCH_SIZE", "20")))
    max_attempts = max(1, int(os.getenv("OUTBOX_MAX_ATTEMPTS", "8")))
    conn = psycopg.connect(database_url())
    try:
        reset_stale(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT public.reconcile_patrimonio_fotos_sheets_outbox(%s)", (limit * 5,))
            reconciled = int(cur.fetchone()[0] or 0)
        conn.commit()
        sheets = sheets_client()
        renewal = renew_expiring_sheet_photo_urls(sheets)
        print(json.dumps({
            "event": "sheets_photo_url_renewal",
            **renewal,
            "expiration_seconds": PHOTO_URL_EXPIRATION_SECONDS,
            "refresh_threshold_seconds": PHOTO_URL_REFRESH_THRESHOLD_SECONDS,
        }, ensure_ascii=False))
        claimed = claim_batch(conn, limit)

        # Vários eventos do mesmo patrimônio são consolidados em uma única
        # sincronização: sync_one já projeta todas as fotos do patrimônio.
        by_patrimonio = {}
        for outbox_id, patrimonio_id, _foto_id in claimed:
            by_patrimonio.setdefault(int(patrimonio_id), []).append(int(outbox_id))

        synced = failed = 0
        for patrimonio_id, event_ids in by_patrimonio.items():
            started = time.monotonic()
            try:
                sync_one(conn, sheets, event_ids[0], patrimonio_id)
                for outbox_id in event_ids:
                    mark(conn, outbox_id, "synced")
                synced += len(event_ids)
                print(json.dumps({
                    "event": "sheets_outbox_sync",
                    "patrimonio_id": patrimonio_id,
                    "outbox_ids": event_ids,
                    "result": "synced",
                    "events_consolidated": len(event_ids),
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                }, ensure_ascii=False))
            except Exception as exc:
                error = _safe_error(exc)
                for outbox_id in event_ids:
                    mark(conn, outbox_id, "failed", error, max_attempts=max_attempts)
                failed += len(event_ids)
                print(json.dumps({
                    "event": "sheets_outbox_sync",
                    "patrimonio_id": patrimonio_id,
                    "outbox_ids": event_ids,
                    "result": "failed",
                    "events_consolidated": len(event_ids),
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "error": error[:500],
                }, ensure_ascii=False))

        print(json.dumps({
            "event": "sheets_outbox_batch",
            "reconciled": reconciled,
            "claimed": len(claimed),
            "patrimonios_processados": len(by_patrimonio),
            "synced": synced,
            "failed": failed,
            "max_attempts": max_attempts,
        }, ensure_ascii=False))
    finally:
        conn.close()

if __name__ == "__main__":
    main()
