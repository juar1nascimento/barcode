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

def test_bloqueia_criacao_automatica_quando_patrimonio_nao_existe_na_aba(monkeypatch):
    import sincronizador_google_sheets as sync

    class FakeWorksheetMissingRow:
        title = "Unidade A"

        def __init__(self):
            self.append_called = False

        def get_all_values(self):
            return [sync.COLUNAS_INVENTARIO + ["ID Patrimônio"]]

        def append_row(self, *args, **kwargs):
            self.append_called = True
            raise AssertionError("Não deve criar linha automaticamente.")

    class FakeSpreadsheet:
        def __init__(self):
            self.worksheet_instance = FakeWorksheetMissingRow()

        def worksheet(self, name):
            return self.worksheet_instance

    spreadsheet = FakeSpreadsheet()
    monkeypatch.setattr(sync, "_buscar_patrimonio", lambda _id: {
        "id": 98654345, "numero": "98654345", "codigo": "", "tipo": "CPU",
        "fabricante": "", "data": "", "unidade": "Unidade A", "setor": "TI",
    })
    monkeypatch.setattr(sync, "conectar_google_sheets", lambda: spreadsheet)
    monkeypatch.setattr(sync, "_sheets_call", lambda _label, operation: operation())

    with pytest.raises(RuntimeError, match="não encontrado.*reconciliação controlada"):
        sync._espelhar_patrimonio({"patrimonio_id": 98654345})

    assert spreadsheet.worksheet_instance.append_called is False

