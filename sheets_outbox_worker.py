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


class DependencyNotReady(RuntimeError):
    """A prerequisite is still being delivered by another asynchronous worker."""


class ReconciliationRequired(RuntimeError):
    """A permanent identity/schema conflict requires controlled human reconciliation."""


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value


def database_url() -> str:
    value = env("DATABASE_URL")
    if value.upper() == "URL":
        raise RuntimeError(
            "DATABASE_URL inválida: a variável contém um placeholder e não "
            "uma conexão PostgreSQL configurada."
        )
    # psycopg aceita tanto uma URI PostgreSQL quanto conninfo key=value.
    # O preparador do CI usa conninfo para evitar expor credenciais em URLs.
    if "://" in value:
        if not value.lower().startswith(("postgresql://", "postgres://")):
            raise RuntimeError("DATABASE_URL inválida: esquema PostgreSQL não suportado.")
    else:
        fields = {part.split("=", 1)[0] for part in value.split() if "=" in part}
        if "host" not in fields or "dbname" not in fields or "user" not in fields:
            raise RuntimeError(
                "DATABASE_URL inválida: informe uma URI PostgreSQL ou um conninfo "
                "com host, dbname e user."
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
    key = env("SUPABASE_SECRET_KEY")
    path = str(storage_path or "").lstrip("/")
    if not path:
        raise RuntimeError("Caminho da foto vazio.")
    endpoint = f"{base}/storage/v1/object/sign/{quote(BUCKET)}/{quote(path, safe='/')}"
    response = requests.post(
        endpoint,
        headers={"apikey": key, "Content-Type": "application/json"},
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


def _sheets_call(operation: str, callback, attempts: int = 4):
    """Execute uma chamada à API Sheets com retry limitado para falhas transitórias."""
    if attempts < 1:
        raise ValueError("attempts deve ser maior que zero.")
    retryable_statuses = {429, 500, 502, 503, 504}
    for attempt in range(attempts):
        try:
            return callback()
        except Exception as exc:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            retryable = (
                status in retryable_statuses
                or isinstance(
                    exc,
                    (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
                )
            )
            if not retryable or attempt + 1 >= attempts:
                raise RuntimeError(
                    f"Google Sheets operation {operation} failed: {_safe_error(exc)}"
                ) from exc
            time.sleep(min(2 ** attempt, 8))


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
        elif status == "dead_letter":
            # A reconciliação manual é necessária; não repetir a mesma escrita externa.
            cur.execute(
                """UPDATE public.patrimonio_fotos_sheets_outbox
                      SET status='dead_letter', processando_em=NULL,
                          proxima_tentativa_em=now(), ultimo_erro=%s,
                          atualizado_em=now()
                    WHERE id=%s""",
                (str(error or "reconciliação controlada necessária")[:2000], outbox_id),
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


def defer_dependency(conn, outbox_id: int, error: str) -> None:
    """Requeue a photo whose Drive URL is not ready without burning retry attempts."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE public.patrimonio_fotos_sheets_outbox
                  SET status='pending',
                      processando_em=NULL,
                      tentativas=GREATEST(tentativas - 1, 0),
                      proxima_tentativa_em=now() + interval '5 minutes',
                      ultimo_erro=%s,
                      atualizado_em=now()
                WHERE id=%s""",
            (str(error or "dependencia ainda não disponível")[:2000], outbox_id),
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


def _normalize_identity(value: object) -> str:
    raw = "" if value is None else str(value)
    return re.sub(r"\s+", " ", raw.strip()).casefold()


def locate_patrimony_row(header: list[str], values: list[list], patrimonio_id: int, numero: str, unidade: str) -> int:
    """Resolve a Sheets row by stable ID; number fallback must be unique and conflict-free."""
    id_positions = [i for i, name in enumerate(header) if str(name).strip() == ID_COLUMN]
    number_positions = [i for i, name in enumerate(header) if str(name).strip() == "Nº de Patrimônio"]
    if len(id_positions) > 1:
        raise ReconciliationRequired(
            f"Aba {unidade} possui coluna {ID_COLUMN} duplicada; reconciliação controlada necessária."
        )
    if len(number_positions) != 1:
        raise ReconciliationRequired(
            f"Aba {unidade} possui coluna Nº de Patrimônio ausente ou ambígua; "
            "reconciliação controlada necessária."
        )

    id_idx = id_positions[0] if id_positions else None
    number_idx = number_positions[0]
    expected_id = _normalize_identity(patrimonio_id)
    expected_number = _normalize_identity(numero)
    if not expected_id or not expected_number:
        raise ReconciliationRequired(
            f"Identidade incompleta para o patrimônio {patrimonio_id}; reconciliação controlada necessária."
        )

    def cell(row, index):
        return row[index] if len(row) > index else ""

    data_rows = list(enumerate(values[1:], start=2))
    if id_idx is not None:
        id_matches = [
            (row_number, row)
            for row_number, row in data_rows
            if _normalize_identity(cell(row, id_idx)) == expected_id
        ]
        if len(id_matches) > 1:
            raise ReconciliationRequired(
                f"ID Patrimônio {patrimonio_id} duplicado na aba {unidade}; "
                "reconciliação controlada necessária."
            )
        if len(id_matches) == 1:
            row_number, row = id_matches[0]
            if _normalize_identity(cell(row, number_idx)) != expected_number:
                raise ReconciliationRequired(
                    f"ID Patrimônio {patrimonio_id} localizado na aba {unidade}, mas o número "
                    "de patrimônio diverge; reconciliação controlada necessária."
                )
            return row_number

    number_matches = [
        (row_number, row)
        for row_number, row in data_rows
        if _normalize_identity(cell(row, number_idx)) == expected_number
    ]
    if len(number_matches) > 1:
        raise ReconciliationRequired(
            f"Número de patrimônio {numero} aparece em múltiplas linhas da aba {unidade}; "
            "reconciliação controlada necessária."
        )
    if len(number_matches) == 1:
        row_number, row = number_matches[0]
        if id_idx is not None:
            existing_id = _normalize_identity(cell(row, id_idx))
            if existing_id and existing_id != expected_id:
                raise ReconciliationRequired(
                    f"Número de patrimônio {numero} aponta para ID {existing_id}, mas o "
                    f"PostgreSQL informa ID {patrimonio_id}; reconciliação controlada necessária."
                )
        return row_number

    raise ReconciliationRequired(
        f"Patrimônio {numero} (ID {patrimonio_id}) não encontrado na aba {unidade}; "
        "sincronização bloqueada para reconciliação controlada."
    )


def locate_photo_columns(header: list[str], unidade: str) -> list[int]:
    """Resolve each photo column exactly once; legacy aliases may not coexist ambiguously."""
    columns = []
    for ordem in range(1, 11):
        candidates = {f"Foto {ordem}", f"Foto {ordem:02d}"}
        matches = [i for i, name in enumerate(header) if str(name).strip() in candidates]
        if len(matches) != 1:
            state = "ausente" if not matches else "ambígua/duplicada"
            raise ReconciliationRequired(
                f"Aba {unidade} possui coluna Foto {ordem} {state}; "
                "reconciliação controlada necessária."
            )
        columns.append(matches[0])
    return columns


def count_dead_letter(conn) -> int:
    """Read-only count so an empty claim batch cannot hide quarantined events."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM public.patrimonio_fotos_sheets_outbox WHERE status='dead_letter'"
        )
        row = cur.fetchone()
    return int(row[0] or 0)


def sync_one(conn, spreadsheet, outbox_id: int, patrimonio_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.id,p.numero_patrimonio,u.nome
                 FROM public.patrimonios p
                 JOIN public.unidades u ON u.id=p.unidade_id
                WHERE p.id=%s""",
            (patrimonio_id,),
        )
        patrimonio = cur.fetchone()
        cur.execute(
            """SELECT ordem, drive_web_url, drive_file_name
                 FROM public.patrimonio_fotos
                WHERE patrimonio_id=%s
                ORDER BY ordem, id""",
            (patrimonio_id,),
        )
        fotos = cur.fetchall()

    if not patrimonio:
        raise RuntimeError(f"Patrimônio {patrimonio_id} não encontrado.")

    _, numero, unidade = patrimonio
    aba = spreadsheet.worksheet(normalize_unit(unidade))
    values = aba.get_all_values()
    if not values:
        raise ReconciliationRequired(
            f"Aba {unidade} sem cabeçalho; reconciliação controlada necessária."
        )

    header = list(values[0])
    row_number = locate_patrimony_row(header, values, patrimonio_id, str(numero), str(unidade))
    photo_columns = locate_photo_columns(header, str(unidade))

    cells = [{"userEnteredValue": {"stringValue": ""}, "textFormatRuns": []} for _ in range(10)]
    for ordem, drive_url, _drive_name in fotos[:10]:
        drive_url = str(drive_url or "").strip()
        if not drive_url:
            raise DependencyNotReady(
                f"Foto {ordem} do patrimônio {patrimonio_id} ainda não possui URL do Google Drive; "
                "evento reagendado sem consumir tentativas."
            )
        index = int(ordem) - 1
        if index < 0 or index >= 10:
            raise RuntimeError(f"Ordem de foto inválida: {ordem}.")
        cells[index] = {
            "userEnteredValue": {"stringValue": f"Foto {int(ordem)}"},
            "textFormatRuns": [{"startIndex": 0, "format": {"link": {"uri": drive_url}}}],
        }

    requests = []
    for index, column_index in enumerate(photo_columns):
        requests.append({
            "updateCells": {
                "start": {"sheetId": aba.id, "rowIndex": row_number - 1, "columnIndex": column_index},
                "rows": [{"values": [cells[index]]}],
                "fields": "userEnteredValue,textFormatRuns",
            }
        })

    _sheets_call("update_photo_rich_text_batch", lambda: spreadsheet.batch_update({"requests": requests}))

    confirmed = aba.batch_get(
        [f"{col_letter(column + 1)}{row_number}" for column in photo_columns],
        value_render_option="FORMULA",
    )
    actual = [str(result[0][0]) if result and result[0] else "" for result in confirmed]
    expected = [f"Foto {int(ordem)}" for ordem, _url, _name in fotos[:10]]
    expected += [""] * (10 - len(expected))
    if actual != expected:
        raise RuntimeError(f"Google Sheets não confirmou os links Rich Text do patrimônio {patrimonio_id}.")

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
        spreadsheet = open_spreadsheet(sheets)
        claimed = claim_batch(conn, limit)

        by_patrimonio = {}
        for outbox_id, patrimonio_id, _foto_id in claimed:
            by_patrimonio.setdefault(int(patrimonio_id), []).append(int(outbox_id))

        synced = failed = deferred = blocked = 0
        for patrimonio_id, event_ids in by_patrimonio.items():
            started = time.monotonic()
            try:
                sync_one(conn, spreadsheet, event_ids[0], patrimonio_id)
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
            except ReconciliationRequired as exc:
                error = _safe_error(exc)
                for outbox_id in event_ids:
                    mark(conn, outbox_id, "dead_letter", error, max_attempts=max_attempts)
                blocked += len(event_ids)
                print(json.dumps({
                    "event": "sheets_outbox_sync",
                    "patrimonio_id": patrimonio_id,
                    "outbox_ids": event_ids,
                    "result": "blocked_reconciliation",
                    "events_consolidated": len(event_ids),
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "error": error[:500],
                }, ensure_ascii=False))
            except DependencyNotReady as exc:
                error = _safe_error(exc)
                for outbox_id in event_ids:
                    defer_dependency(conn, outbox_id, error)
                deferred += len(event_ids)
                print(json.dumps({
                    "event": "sheets_outbox_sync",
                    "patrimonio_id": patrimonio_id,
                    "outbox_ids": event_ids,
                    "result": "deferred",
                    "events_consolidated": len(event_ids),
                    "retry_after_seconds": 300,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "error": error[:500],
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

        dead_letter_count = count_dead_letter(conn)
        print(json.dumps({
            "event": "sheets_outbox_batch",
            "reconciled": reconciled,
            "claimed": len(claimed),
            "patrimonios_processados": len(by_patrimonio),
            "synced": synced,
            "deferred": deferred,
            "failed": failed,
            "blocked_reconciliation": blocked,
            "dead_letter_count": dead_letter_count,
            "max_attempts": max_attempts,
        }, ensure_ascii=False))
        # Um lote vazio não significa fila saudável: dead-letter permanece bloqueador.
        if failed or blocked or dead_letter_count:
            raise SystemExit(2)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
