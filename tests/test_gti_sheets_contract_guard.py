"""Isolated regression tests for the GTI SESA Sheets contract guard.

These tests use synthetic headers only. They do not connect to Google Sheets,
PostgreSQL, Drive, or production credentials.
"""
from pathlib import Path

import pytest

from inventario_sheets_outbox_worker import (
    _canonical_header_positions,
    preflight_inventory_sheets,
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


def test_worker_preserves_optional_barcode_column():
    positions = _canonical_header_positions(CANONICAL + ["Código de Barras"])
    assert positions["Código de Barras"] == 5


def test_worker_blocks_duplicate_optional_barcode_column():
    with pytest.raises(RuntimeError, match="Código de Barras.*colunas 6 e 7"):
        _canonical_header_positions(CANONICAL + ["Código de Barras", "Código de Barras"])


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



def test_inventory_preflight_blocks_unclassified_tabs(monkeypatch):
    import google_sheets_schema

    monkeypatch.setattr(
        google_sheets_schema,
        "auditar_e_padronizar_abas_inventario",
        lambda spreadsheet, aplicar=False: {
            "abas_verificadas": 40,
            "abas_bloqueadas": 0,
            "erros": [],
            "detalhes": [],
            "abas_nao_reconhecidas": ["UBS Unidade Nova"],
        },
    )

    with pytest.raises(RuntimeError, match="Nenhum item foi consumido"):
        preflight_inventory_sheets(FakeSpreadsheet(FakeWorksheet([CANONICAL])))


def test_inventory_preflight_accepts_explicit_technical_tabs(monkeypatch):
    import google_sheets_schema

    monkeypatch.setattr(
        google_sheets_schema,
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

    report = preflight_inventory_sheets(FakeSpreadsheet(FakeWorksheet([CANONICAL])))

    assert report["abas_verificadas"] == 40
    assert report["abas_bloqueadas"] == 0

def test_legacy_photo_header_normalization_matches_numeric_suffix(monkeypatch):
    import sincronizador_google_sheets as sync

    class Worksheet:
        def __init__(self):
            self.headers = ["Foto 1", "Foto 02", "Foto 10", "Foto 13"]
            self.updated = None

        def row_values(self, row):
            assert row == 1
            return self.headers

        def update(self, **kwargs):
            self.updated = kwargs["values"][0]

    worksheet = Worksheet()
    monkeypatch.setattr(sync, "_sheets_call", lambda label, operation: operation())

    headers = sync._normalizar_cabecalhos_fotos(worksheet)

    assert headers == ["Foto 01", "Foto 02", "Foto 10", "Foto 13"]
    assert worksheet.updated == headers



class FakeInventoryWorksheet:
    title = "URS Teste"

    def __init__(self, values):
        self.values = [list(row) for row in values]

    def get_all_values(self):
        return [list(row) for row in self.values]

    def append_row(self, values, **kwargs):
        self.values.append(list(values))

    def update(self, *, values, range_name, **kwargs):
        import re
        match = re.fullmatch(r"A(\d+):([A-Z]+)(\d+)", range_name)
        assert match is not None
        row_number = int(match.group(1))
        while len(self.values) < row_number:
            self.values.append([])
        self.values[row_number - 1] = list(values[0])


def _prepare_inventory_mirror(monkeypatch, worksheet):
    import sincronizador_google_sheets as sync

    monkeypatch.setattr(
        sync, "_buscar_patrimonio",
        lambda patrimonio_id: {
            "id": patrimonio_id, "numero": "GTI-TEST-01", "codigo": "BC-01",
            "tipo": "Computador", "fabricante": "Dell", "data": "2026-10-12",
            "unidade": "URS Teste", "setor": "TI",
        },
    )
    monkeypatch.setattr(sync, "conectar_google_sheets", lambda: object())
    monkeypatch.setattr(sync, "_obter_aba_gravacao", lambda *args: worksheet)
    monkeypatch.setattr(sync, "_normalizar_unidade_aba", lambda value: value)
    monkeypatch.setattr(sync, "_garantir_coluna_patrimonio_texto", lambda aba: None)
    monkeypatch.setattr(sync, "_garantir_cabecalho_moderno", lambda aba: True)
    monkeypatch.setattr(sync, "_sheets_call", lambda label, operation: operation())


def test_inventory_mirror_confirms_row_after_append(monkeypatch):
    import sincronizador_google_sheets as sync

    worksheet = FakeInventoryWorksheet([CANONICAL + ["Código de Barras"]])
    _prepare_inventory_mirror(monkeypatch, worksheet)

    sync._espelhar_patrimonio({"patrimonio_id": 123})

    assert len(worksheet.values) == 2
    assert worksheet.values[1][:6] == ["TI", "Computador", "GTI-TEST-01", "Dell", "2026-10-12", "BC-01"]


def test_inventory_mirror_fails_when_readback_values_do_not_match(monkeypatch):
    import sincronizador_google_sheets as sync

    class NonPersistingWorksheet(FakeInventoryWorksheet):
        def update(self, *, values, range_name, **kwargs):
            # Simula uma API que não persiste a alteração; a releitura deve detectar.
            return None

    worksheet = NonPersistingWorksheet([
        CANONICAL + ["Código de Barras"],
        ["TI", "Computador", "GTI-TEST-01", "Outro fabricante", "2026-10-12", "BC-01"],
    ])
    _prepare_inventory_mirror(monkeypatch, worksheet)

    with pytest.raises(RuntimeError, match="não confirmou o campo"):
        sync._espelhar_patrimonio({"patrimonio_id": 123})


def test_inventory_mirror_fails_when_duplicate_rows_match_number(monkeypatch):
    import sincronizador_google_sheets as sync

    row = ["TI", "Computador", "GTI-TEST-01", "Dell", "2026-10-12", "BC-01"]
    worksheet = FakeInventoryWorksheet([CANONICAL + ["Código de Barras"], row, row])
    _prepare_inventory_mirror(monkeypatch, worksheet)

    with pytest.raises(RuntimeError, match="não confirmou uma única linha"):
        sync._espelhar_patrimonio({"patrimonio_id": 123})
