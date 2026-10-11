"""Isolated regression tests for the GTI SESA Sheets contract guard.

These tests use synthetic headers only. They do not connect to Google Sheets,
PostgreSQL, Drive, or production credentials.
"""
from pathlib import Path

import pytest

from inventario_sheets_outbox_worker import (
    _canonical_header_positions,
)
from google_sheets_schema import (
    _canonicalize_values,
    auditar_e_padronizar_abas_inventario,
)


CANONICAL = [
    "Setor",
    "Tipo de Patrimônio",
    "Nº de Patrimônio",
    "Fabricante",
    "Data Cadastro",
]


def test_worker_accepts_unique_canonical_headers():
    positions = _canonical_header_positions(CANONICAL)
    assert positions == {name: index for index, name in enumerate(CANONICAL)}


def test_worker_blocks_duplicate_data_cadastro_headers():
    header = CANONICAL + ["Data Cadastro"]
    with pytest.raises(RuntimeError, match="Data Cadastro.*colunas 5 e 6"):
        _canonical_header_positions(header)


def test_worker_blocks_local_setor_ambiguity():
    header = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio",
              "Fabricante", "Data Cadastro", "Local / Setor"]
    with pytest.raises(RuntimeError, match="Setor.*colunas 1 e 6"):
        _canonical_header_positions(header)


def test_schema_reports_duplicate_data_cadastro_without_selecting_silently():
    rows, info = _canonicalize_values([
        CANONICAL + ["Data Cadastro"],
        ["TI", "Computador", "GTI-001", "Dell", "2026-01-02", ""],
    ])
    assert "Data Cadastro" in info["conflicts"]
    assert info["changed"] is True
    # The auditor's existing conflict gate must block applying this row.
    assert rows[0].count("Data Cadastro") == 1


def test_schema_reports_local_setor_as_ambiguous():
    header = CANONICAL + ["Local / Setor"]
    _, info = _canonicalize_values([
        header,
        ["TI", "Computador", "GTI-002", "Dell", "2026-01-03", "Sala 2"],
    ])
    assert "Setor" in info["conflicts"]



class FakeWorksheet:
    title = "URS Novo Horizonte"

    def __init__(self, values):
        self.values = values
        self.update_calls = 0

    def get_all_values(self, value_render_option=None):
        return self.values

    def update(self, **kwargs):
        self.update_calls += 1


class FakeSpreadsheet:
    def __init__(self, worksheet):
        self.worksheet = worksheet
        self.batch_update_calls = 0

    def worksheets(self):
        return [self.worksheet]

    def batch_update(self, payload):
        self.batch_update_calls += 1


def test_schema_audit_only_mode_performs_no_sheet_writes():
    worksheet = FakeWorksheet([CANONICAL, ["TI", "Computador", "X-1", "Dell", "2026-01-02"]])
    spreadsheet = FakeSpreadsheet(worksheet)

    report = auditar_e_padronizar_abas_inventario(spreadsheet, aplicar=False)

    assert report["abas_verificadas"] == 1
    assert worksheet.update_calls == 0
    assert spreadsheet.batch_update_calls == 0

def test_manual_sync_workflow_never_enables_validation_removal():
    workflow = Path(".github/workflows/inventario-sync.yml").read_text(
        encoding="utf-8"
    )
    assert 'SHEETS_REMOVE_VALIDATIONS: "false"' in workflow
    assert 'SHEETS_REMOVE_VALIDATIONS: "true"' not in workflow
