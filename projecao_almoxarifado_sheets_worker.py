"""Sincroniza a projeção do Almoxarifado Central para uma aba analítica do Google Sheets.

PostgreSQL/Supabase continua sendo a fonte de verdade. A aba
"Projecao_Almoxarifado" é somente um espelho para o Looker Studio.
A sincronização é idempotente: cada execução reconstrói o conteúdo da aba
a partir da view operacional, sem alterar o inventário nem os eventos.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

import gspread
import psycopg
from google.oauth2.service_account import Credentials


SHEET_NAME = "Projecao_Almoxarifado"
COLUMNS = [
    "Meta ID",
    "Unidade ID",
    "Unidade",
    "Tipo",
    "Tipo Custom",
    "Fabricante",
    "Quantidade Total",
    "Quantidade Conferida",
    "Quantidade Restante",
    "Percentual Concluido",
    "Status Projecao",
    "Atualizado Em",
]


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value


def safe_error(error: Exception | str) -> str:
    value = str(error or "")
    value = re.sub(r"(?i)(postgres(?:ql)?://)[^\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(token=)[^&\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", "[REDACTED PEM]", value, flags=re.DOTALL)
    return value[:500]


def database_url() -> str:
    host = env("GTI_DB_HOST")
    name = env("GTI_DB_NAME")
    user = env("GTI_DB_USER")
    password = env("GTI_DB_PASSWORD")
    return (
        f"host={host} dbname={name} user={user} password={password} "
        "sslmode=require"
    )


def sheets_client():
    data = json.loads(env("GOOGLE_SERVICE_ACCOUNT_JSON"))
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    return gspread.authorize(
        Credentials.from_service_account_info(data, scopes=scopes)
    )


def open_spreadsheet(client):
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "").strip()
    spreadsheet_url = os.getenv("GOOGLE_SPREADSHEET_URL", "").strip()
    if spreadsheet_id:
        return client.open_by_key(spreadsheet_id)
    if spreadsheet_url:
        return client.open_by_url(spreadsheet_url)
    raise RuntimeError("Defina GOOGLE_SPREADSHEET_ID ou GOOGLE_SPREADSHEET_URL.")


def fetch_projection(conn) -> list[list[object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                meta_id,
                unidade_id,
                unidade,
                tipo,
                tipo_custom,
                fabricante,
                quantidade_total,
                quantidade_conferida,
                quantidade_restante,
                percentual_concluido,
                CASE
                    WHEN quantidade_total IS NULL THEN 'SEM_META'
                    WHEN quantidade_restante = 0 THEN 'CONCLUIDA'
                    ELSE 'EM_ANDAMENTO'
                END AS status_projecao,
                atualizado_em
            FROM public.v_projecao_almoxarifado_central
            WHERE unidade_id = 2
              AND ativo = TRUE
            ORDER BY tipo, tipo_custom, fabricante, meta_id
            """
        )
        rows = cur.fetchall()

    output = [COLUMNS]
    for row in rows:
        values = []
        for value in row:
            if isinstance(value, datetime):
                values.append(value.isoformat(sep=" ", timespec="seconds"))
            else:
                values.append(value)
        output.append(values)
    return output


def sync_sheet(spreadsheet, values: list[list[object]]) -> dict:
    try:
        worksheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=SHEET_NAME,
            rows=max(100, len(values) + 10),
            cols=len(COLUMNS),
        )

    required_rows = max(100, len(values) + 10)
    if worksheet.row_count < required_rows or worksheet.col_count < len(COLUMNS):
        worksheet.resize(
            rows=max(worksheet.row_count, required_rows),
            cols=max(worksheet.col_count, len(COLUMNS)),
        )

    worksheet.clear()
    end_col = _column_letter(len(COLUMNS))
    worksheet.update(
        values=values,
        range_name=f"A1:{end_col}{len(values)}",
        value_input_option="USER_ENTERED",
    )
    worksheet.freeze(rows=1)
    worksheet.format(
        f"A1:{end_col}1",
        {"textFormat": {"bold": True}, "horizontalAlignment": "CENTER"},
    )

    return {
        "aba": SHEET_NAME,
        "linhas": max(0, len(values) - 1),
        "colunas": len(COLUMNS),
    }


def _column_letter(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def main():
    conn = psycopg.connect(database_url())
    try:
        values = fetch_projection(conn)
    finally:
        conn.close()

    spreadsheet = open_spreadsheet(sheets_client())
    result = sync_sheet(spreadsheet, values)
    print(json.dumps({
        "event": "projecao_almoxarifado_sheets_sync",
        "result": "synced",
        **result,
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "event": "projecao_almoxarifado_sheets_sync",
            "result": "failed",
            "error": safe_error(exc),
        }, ensure_ascii=False))
        raise
