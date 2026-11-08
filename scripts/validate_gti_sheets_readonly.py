"""Read-only validation of the GTI Google Sheets header contract.

This module reads worksheet titles and first-row headers only. It never reads
patrimony rows and never writes to Google Sheets.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

import gspread
from google.oauth2.service_account import Credentials


READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
REQUIRED_HEADERS = (
    "Setor",
    "Tipo de Patrimônio",
    "Nº de Patrimônio",
    "Fabricante",
    "Data Cadastro",
)
HEADER_ALIASES = {
    "setor": "Setor",
    "tipo de patrimonio": "Tipo de Patrimônio",
    "tipo patrimonio": "Tipo de Patrimônio",
    "n de patrimonio": "Nº de Patrimônio",
    "n patrimonio": "Nº de Patrimônio",
    "numero de patrimonio": "Nº de Patrimônio",
    "numero patrimonio": "Nº de Patrimônio",
    "fabricante": "Fabricante",
    "data cadastro": "Data Cadastro",
    "data de cadastro": "Data Cadastro",
}


def header_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", without_marks.casefold()).strip()


def inspect_header(header: list[str]) -> tuple[bool, list[str]]:
    """Return whether this is an inventory tab and which required headers are missing."""
    found = set()
    for value in header:
        key = header_key(value)
        canonical = HEADER_ALIASES.get(key)
        if canonical:
            found.add(canonical)
    # Avoid treating unrelated dashboard/support tabs as inventory tabs.
    if len(found) < 2:
        return False, []
    return True, [name for name in REQUIRED_HEADERS if name not in found]


def main() -> None:
    raw_credentials = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "").strip()
    if not raw_credentials or not spreadsheet_id:
        raise SystemExit("Credenciais Google ou ID da planilha ausentes.")

    try:
        service_account = json.loads(raw_credentials)
    except json.JSONDecodeError:
        raise SystemExit("Credencial Google inválida: JSON não interpretável.") from None

    credentials = Credentials.from_service_account_info(
        service_account,
        scopes=[READONLY_SCOPE],
    )
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)

    worksheets_scanned = 0
    inventory_tabs = 0
    invalid_tabs = 0
    for worksheet in spreadsheet.worksheets():
        worksheets_scanned += 1
        header = worksheet.row_values(1)
        is_inventory, missing = inspect_header(header)
        if not is_inventory:
            continue
        inventory_tabs += 1
        if missing:
            invalid_tabs += 1

    print(
        "Google Sheets read-only validation: "
        f"worksheets_scanned={worksheets_scanned}, "
        f"inventory_tabs={inventory_tabs}, invalid_tabs={invalid_tabs}, "
        f"external_write=false, data_rows_read=0."
    )
    if inventory_tabs == 0:
        raise SystemExit("Nenhuma aba com contrato de inventário foi identificada.")
    if invalid_tabs:
        raise SystemExit(
            f"{invalid_tabs} aba(s) de inventário não atendem ao contrato de cabeçalhos."
        )


if __name__ == "__main__":
    main()
