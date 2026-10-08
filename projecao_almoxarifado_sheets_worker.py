"""Publica a projeção do Almoxarifado Central no Google Sheets para o Data Studio.
O Supabase permanece como fonte de verdade. A sincronização é idempotente.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from decimal import Decimal

import gspread
import psycopg
from google.oauth2.service_account import Credentials


DETAIL_SHEET_NAME = "Projecao_Almoxarifado"
SUMMARY_SHEET_NAME = "Projecao_Almoxarifado_Resumo"

COLUMNS = [
    "Meta ID", "Unidade ID", "Unidade", "Tipo", "Tipo Custom", "Fabricante",
    "Quantidade Total", "Quantidade Conferida", "Quantidade Restante",
    "Percentual Concluido", "Status Projecao", "Atualizado Em",
]

SUMMARY_COLUMNS = [
    "Unidade ID", "Unidade", "Metas Ativas", "Metas com Quantidade",
    "Quantidade Total Definida", "Quantidade Conferida", "Quantidade Restante",
    "Metas sem Quantidade", "Metas Concluidas", "Metas em Andamento",
    "Percentual Concluido", "Atualizado Em",
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
    value = re.sub(
        r"-----BEGIN [^-]+-----.*?-----END [^-]+-----",
        "[REDACTED PEM]",
        value,
        flags=re.DOTALL,
    )
    return value[:500]


def database_url() -> str:
    return (
        f"host={env('GTI_DB_HOST')} dbname={env('GTI_DB_NAME')} "
        f"user={env('GTI_DB_USER')} password={env('GTI_DB_PASSWORD')} "
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


def normalize_value(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def normalize_rows(rows: list[tuple], columns: list[str]) -> list[list[object]]:
    output = [columns]
    for row in rows:
        output.append([normalize_value(value) for value in row])
    return output


def fetch_projection(conn) -> list[list[object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT meta_id, unidade_id, unidade, tipo, tipo_custom, fabricante,
                   quantidade_total, quantidade_conferida, quantidade_restante,
                   percentual_concluido,
                   CASE
                     WHEN quantidade_total IS NULL THEN 'SEM_META'
                     WHEN quantidade_restante = 0 THEN 'CONCLUIDA'
                     ELSE 'EM_ANDAMENTO'
                   END AS status_projecao,
                   atualizado_em
            FROM public.v_projecao_almoxarifado_central
            WHERE unidade_id = 2 AND ativo = TRUE
            ORDER BY tipo, tipo_custom, fabricante, meta_id
            """
        )
        return normalize_rows(cur.fetchall(), COLUMNS)


def fetch_projection_summary(conn) -> list[list[object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT unidade_id, unidade, metas_ativas, metas_com_quantidade,
                   quantidade_total_definida, quantidade_conferida,
                   quantidade_restante, metas_sem_quantidade, metas_concluidas,
                   metas_em_andamento, percentual_concluido, atualizado_em
            FROM public.v_projecao_almoxarifado_central_resumo
            """
        )
        return normalize_rows(cur.fetchall(), SUMMARY_COLUMNS)


def sync_sheet(
    spreadsheet, values: list[list[object]], sheet_name: str, columns: list[str]
) -> dict:
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=max(100, len(values) + 10),
            cols=len(columns),
        )

    required_rows = max(100, len(values) + 10)
    if worksheet.row_count < required_rows or worksheet.col_count < len(columns):
        worksheet.resize(
            rows=max(worksheet.row_count, required_rows),
            cols=max(worksheet.col_count, len(columns)),
        )

    worksheet.clear()
    end_col = column_letter(len(columns))
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
        "aba": sheet_name,
        "linhas": max(0, len(values) - 1),
        "colunas": len(columns),
    }


def column_letter(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def main():
    conn = psycopg.connect(database_url())
    try:
        detail_values = fetch_projection(conn)
        summary_values = fetch_projection_summary(conn)
    finally:
        conn.close()

    spreadsheet = open_spreadsheet(sheets_client())
    detail_result = sync_sheet(
        spreadsheet, detail_values, DETAIL_SHEET_NAME, COLUMNS
    )
    summary_result = sync_sheet(
        spreadsheet, summary_values, SUMMARY_SHEET_NAME, SUMMARY_COLUMNS
    )
    print(
        json.dumps(
            {
                "event": "projecao_almoxarifado_sheets_sync",
                "result": "synced",
                "abas": [detail_result, summary_result],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "event": "projecao_almoxarifado_sheets_sync",
                    "result": "failed",
                    "error": safe_error(exc),
                },
                ensure_ascii=False,
            )
        )
        raise
