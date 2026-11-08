import pytest

from scripts.validate_gti_sheets_readonly import inspect_header


def test_inventory_header_accepts_accent_and_legacy_aliases():
    is_inventory, missing = inspect_header([
        "Setor",
        "Tipo Patrimonio",
        "Número de Patrimonio",
        "Fabricante",
        "Data de Cadastro",
    ])

    assert is_inventory is True
    assert missing == []


def test_inventory_header_reports_missing_required_columns():
    is_inventory, missing = inspect_header([
        "Setor",
        "Nº de Patrimônio",
        "Fabricante",
    ])

    assert is_inventory is True
    assert missing == ["Tipo de Patrimônio", "Data Cadastro"]


def test_unrelated_worksheet_is_ignored():
    is_inventory, missing = inspect_header(["Métrica", "Total", "Atualizado em"])

    assert is_inventory is False
    assert missing == []
