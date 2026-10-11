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
from sheets_outbox_worker import preflight_photo_headers


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


def test_sync_preflight_blocks_before_claiming_any_outbox_item(monkeypatch):
    import sincronizador_google_sheets as sync

    monkeypatch.setenv("SHEETS_REMOVE_VALIDATIONS", "false")
    monkeypatch.setattr(sync, "conectar_google_sheets", lambda: object())
    monkeypatch.setattr(
        sync,
        "auditar_e_padronizar_abas_inventario",
        lambda spreadsheet, aplicar=False: {
            "abas_verificadas": 1,
            "abas_bloqueadas": 1,
            "erros": [],
            "detalhes": [
                {
                    "aba": "UBS André Carloni",
                    "alteracao_necessaria": True,
                    "conflitos": ["Setor"],
                    "status": "bloqueada_por_cabecalho_duplicado",
                }
            ],
        },
    )
    monkeypatch.setattr(
        sync,
        "_claim",
        lambda tabela, limit: pytest.fail(
            f"outbox não deveria ser consumido: {tabela}"
        ),
    )

    with pytest.raises(RuntimeError, match="preflight somente leitura"):
        sync.processar_fila_google_sheets(limit=1)


def test_schema_audit_only_mode_reports_ambiguous_headers_without_writes():
    worksheet = FakeWorksheet([
        CANONICAL + ["Data Cadastro"],
        ["TI", "Computador", "X-2", "Dell", "2026-01-02", "legacy-date"],
    ])
    spreadsheet = FakeSpreadsheet(worksheet)

    report = auditar_e_padronizar_abas_inventario(spreadsheet, aplicar=False)

    assert report["abas_bloqueadas"] == 1
    assert report["detalhes"][0]["conflitos"] == ["Data Cadastro"]
    assert worksheet.update_calls == 0
    assert spreadsheet.batch_update_calls == 0



def test_sync_preflight_blocks_unclassified_tabs_before_claiming_outbox(monkeypatch):
    import sincronizador_google_sheets as sync

    monkeypatch.setenv("SHEETS_REMOVE_VALIDATIONS", "false")
    monkeypatch.setattr(sync, "conectar_google_sheets", lambda: object())
    monkeypatch.setattr(
        sync,
        "auditar_e_padronizar_abas_inventario",
        lambda spreadsheet, aplicar=False: {
            "abas_verificadas": 40,
            "abas_bloqueadas": 0,
            "erros": [],
            "detalhes": [],
            "abas_nao_reconhecidas": ["UBS Unidade Nova"],
        },
    )
    monkeypatch.setattr(
        sync,
        "_claim",
        lambda tabela, limit: pytest.fail(
            f"outbox não deveria ser consumido: {tabela}"
        ),
    )

    with pytest.raises(RuntimeError, match="sem classificação aprovada"):
        sync.processar_fila_google_sheets(limit=1)


def test_sync_preflight_allows_only_explicit_technical_tabs(monkeypatch):
    import sincronizador_google_sheets as sync

    monkeypatch.setenv("SHEETS_REMOVE_VALIDATIONS", "false")
    monkeypatch.setattr(sync, "conectar_google_sheets", lambda: object())
    monkeypatch.setattr(
        sync,
        "auditar_e_padronizar_abas_inventario",
        lambda spreadsheet, aplicar=False: {
            "abas_verificadas": 40,
            "abas_bloqueadas": 0,
            "erros": [],
            "detalhes": [],
            "abas_nao_reconhecidas": [
                "_AUDITORIA_CABECALHOS",
                "Projecao_Almoxarifado",
                "Projecao_Almoxarifado_Resumo",
            ],
        },
    )
    claimed = []
    monkeypatch.setattr(sync, "_claim", lambda tabela, limit: claimed.append(tabela) or [])
    result = sync.processar_fila_google_sheets(limit=1)

    assert result["processados"] == 0
    assert claimed == ["patrimonios_sheets_outbox", "patrimonio_fotos_sheets_outbox"]



def test_photo_preflight_accepts_unique_required_columns():
    header = ["Nº de Patrimônio"] + [f"Foto {i:02d}" for i in range(1, 11)]
    spreadsheet = FakeSpreadsheet(FakeWorksheet([header]))

    report = preflight_photo_headers(spreadsheet)

    assert report == {"abas_verificadas": 1, "abas_com_erro": 0}


def test_photo_preflight_blocks_duplicate_legacy_photo_header():
    header = ["Nº de Patrimônio"] + [f"Foto {i:02d}" for i in range(1, 11)] + ["Foto 1"]
    spreadsheet = FakeSpreadsheet(FakeWorksheet([header]))

    with pytest.raises(RuntimeError, match="cabeçalhos duplicados.*Foto 01"):
        preflight_photo_headers(spreadsheet)


def test_photo_preflight_blocks_missing_photo_columns():
    header = ["Nº de Patrimônio"] + [f"Foto {i:02d}" for i in range(1, 10)]
    spreadsheet = FakeSpreadsheet(FakeWorksheet([header]))

    with pytest.raises(RuntimeError, match="colunas obrigatórias ausentes.*Foto 10"):
        preflight_photo_headers(spreadsheet)
