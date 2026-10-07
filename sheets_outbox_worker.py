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

    # Este worker não cria, renomeia ou reorganiza cabeçalhos.
    # A estrutura da aba é tratada por gate/auditoria separado.
    if "Nº de Patrimônio" not in header:
        raise RuntimeError(f"Aba {unidade} não possui a coluna Nº de Patrimônio.")

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

    photo_columns = []
    for ordem in range(1, 11):
        candidates = (f"Foto {ordem}", f"Foto {ordem:02d}")
        found = next((h for h in candidates if h in header), None)
        if found is None:
            raise RuntimeError(f"Aba {unidade} não possui a coluna Foto {ordem}.")
        photo_columns.append(header.index(found))

    cells = [{"userEnteredValue": {"stringValue": ""}, "textFormatRuns": []} for _ in range(10)]
    for ordem, drive_url, _drive_name in fotos[:10]:
        drive_url = str(drive_url or "").strip()
        if not drive_url:
            raise RuntimeError(
                f"Foto {ordem} do patrimônio {patrimonio_id} ainda não possui URL do Google Drive."
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
                "start": {
                    "sheetId": aba.id,
                    "rowIndex": row_number - 1,
                    "columnIndex": column_index,
                },
                "rows": [{"values": [cells[index]]}],
                "fields": "userEnteredValue,textFormatRuns",
            }
        })

    _sheets_call(
        "update_photo_rich_text_batch",
        lambda: spreadsheet.batch_update({"requests": requests}),
    )

    confirmed = aba.batch_get(
        [f"{col_letter(column + 1)}{row_number}" for column in photo_columns],
        value_render_option="FORMULA",
    )
    actual = [
        str(result[0][0]) if result and result[0] else ""
        for result in confirmed
    ]
    expected = [
        f"Foto {int(ordem)}" if int(ordem) <= 10 else ""
        for ordem, _url, _name in fotos[:10]
    ]
    expected += [""] * (10 - len(expected))
    if actual != expected:
        raise RuntimeError(
            f"Google Sheets não confirmou os links Rich Text do patrimônio {patrimonio_id}."
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
        spreadsheet = open_spreadsheet(sheets_client())
        claimed = claim_batch(conn, limit)

        by_patrimonio = {}
        for outbox_id, patrimonio_id, _foto_id in claimed:
            by_patrimonio.setdefault(int(patrimonio_id), []).append(int(outbox_id))

        synced = failed = 0
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
