import pytest

from sincronizador_google_sheets import (
    _localizar_linha_patrimonio,
    _obter_aba_existente_para_sync,
)


class FakeWorksheet:
    title = "UBS Teste"

    def get_all_values(self):
        raise AssertionError("Os valores foram fornecidos ao helper; não deveria reler a planilha.")


def test_localiza_por_id_estavel_mesmo_com_numero_repetido():
    values = [
        ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Fabricante", "Data Cadastro", "Código de Barras", "ID Patrimônio"],
        ["Sala A", "CPU", "PAT-01", "Fabricante A", "", "", "101"],
        ["Sala B", "CPU", "PAT-01", "Fabricante B", "", "", "202"],
    ]
    result = _localizar_linha_patrimonio(
        FakeWorksheet(), {"id": 202, "numero": "PAT-01"}, values
    )
    assert result == 3


def test_fallback_por_numero_unico_quando_id_ainda_nao_preenchido():
    values = [
        ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Fabricante", "Data Cadastro", "Código de Barras", "ID Patrimônio"],
        ["Sala A", "CPU", "PAT-02", "Fabricante A", "", "", ""],
    ]
    result = _localizar_linha_patrimonio(
        FakeWorksheet(), {"id": 303, "numero": "PAT-02"}, values
    )
    assert result == 2


def test_bloqueia_numero_duplicado_sem_id_correspondente():
    values = [
        ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Fabricante", "Data Cadastro", "Código de Barras", "ID Patrimônio"],
        ["Sala A", "CPU", "PAT-03", "Fabricante A", "", "", ""],
        ["Sala B", "CPU", "PAT-03", "Fabricante B", "", "", ""],
    ]
    with pytest.raises(RuntimeError, match="múltiplas linhas"):
        _localizar_linha_patrimonio(
            FakeWorksheet(), {"id": 404, "numero": "PAT-03"}, values
        )


def test_bloqueia_numero_que_aponta_para_outro_id():
    values = [
        ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Fabricante", "Data Cadastro", "Código de Barras", "ID Patrimônio"],
        ["Sala A", "CPU", "PAT-04", "Fabricante A", "", "", "999"],
    ]
    with pytest.raises(RuntimeError, match="aponta para ID"):
        _localizar_linha_patrimonio(
            FakeWorksheet(), {"id": 505, "numero": "PAT-04"}, values
        )


class WorksheetNotFound(Exception):
    pass


class FakeSpreadsheetMissingWorksheet:
    def __init__(self):
        self.add_called = False

    def worksheet(self, name):
        raise WorksheetNotFound(name)

    def add_worksheet(self, **kwargs):
        self.add_called = True
        raise AssertionError("A sincronização não deve criar abas automaticamente.")


def test_bloqueia_aba_ausente_sem_tentar_cria_la():
    spreadsheet = FakeSpreadsheetMissingWorksheet()
    with pytest.raises(RuntimeError, match="criação e validação estrutural controladas"):
        _obter_aba_existente_para_sync(spreadsheet, "UBS Ausente")
    assert spreadsheet.add_called is False
