import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Tabela_de_dados_Inventario_7_2 as backend


def test_schema_e_tipo_patrimonio():
    assert backend.COLUNAS_INVENTARIO == [
        "Setor",
        "Tipo de Patrimônio",
        "Nº de Patrimônio",
        "Fabricante",
        "Data Cadastro",
    ]
    assert "Código de Barras" not in backend.COLUNAS_INVENTARIO
    assert "Origem" not in backend.COLUNAS_INVENTARIO
    assert "Status" not in backend.COLUNAS_INVENTARIO
    assert backend.TIPOS_PATRIMONIO == (
        "CPU",
        "Monitores",
        "Teclado",
        "Mouse",
        "Imprenssoras",
        "Outros Dispositivos",
    )


def test_normalizacao_legacy_converte_varios_tipos():
    df = pd.DataFrame(
        [
            {"Setor": "Farmacia", "Computador": "PAT-001", "Fabricante Computador": "Dell", "Monitor": "MON-001"},
            {"Setor": "Farmacia", "Monitor": "MON-002", "Fabricante Monitor": "HP"},
        ]
    )
    normalizado = backend._normalizar_legacy_dataframe(df)

    assert len(normalizado) == 3
    assert set(normalizado["Tipo de Patrimônio"]) == {"CPU", "Monitores"}
    assert set(normalizado["Nº de Patrimônio"]) == {"PAT-001", "MON-001", "MON-002"}
    assert list(normalizado.columns) == backend.COLUNAS_INVENTARIO


def test_registro_usa_codigo_lido_como_numero_de_patrimonio(monkeypatch):
    estado = {"df": pd.DataFrame(columns=backend.COLUNAS_INVENTARIO)}
    avisos = []

    monkeypatch.setattr(backend, "carregar_dados_excel", lambda unidade: (estado["df"].copy(), "teste"))
    monkeypatch.setattr(backend, "salvar_no_excel", lambda df, unidade: estado.__setitem__("df", df.copy()) or True)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: avisos.append(mensagem))

    assert backend.registrar_patrimonio("789000000001", "Monitores", "Farmacia", "UBS Teste", "Dell")
    assert backend.registrar_patrimonio("789000000002", "Monitores", "Farmacia", "UBS Teste", "HP")

    assert len(estado["df"]) == 2
    assert set(estado["df"]["Nº de Patrimônio"]) == {"789000000001", "789000000002"}
    assert "Código de Barras" not in estado["df"].columns
    assert "Origem" not in estado["df"].columns
    assert "Status" not in estado["df"].columns
    assert avisos == []


def test_registro_bloqueia_numero_de_patrimonio_duplicado(monkeypatch):
    estado = {
        "df": pd.DataFrame(
            [{
                "Setor": "Farmacia",
                "Tipo de Patrimônio": "Monitores",
                "Nº de Patrimônio": "789000000001",
                "Fabricante": "Dell",
                "Data Cadastro": "",
            }],
            columns=backend.COLUNAS_INVENTARIO,
        )
    }
    avisos = []
    monkeypatch.setattr(backend, "carregar_dados_excel", lambda unidade: (estado["df"].copy(), "teste"))
    monkeypatch.setattr(backend, "salvar_no_excel", lambda df, unidade: estado.__setitem__("df", df.copy()) or True)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: avisos.append(mensagem))

    assert not backend.registrar_patrimonio("789000000001", "Monitores", "Farmacia", "UBS Teste", "HP")
    assert len(estado["df"]) == 1
    assert avisos


def test_todos_os_seis_tipos_podem_ser_cadastrados(monkeypatch):
    estado = {"df": pd.DataFrame(columns=backend.COLUNAS_INVENTARIO)}
    monkeypatch.setattr(backend, "carregar_dados_excel", lambda unidade: (estado["df"].copy(), "teste"))
    monkeypatch.setattr(backend, "salvar_no_excel", lambda df, unidade: estado.__setitem__("df", df.copy()) or True)

    for indice, tipo in enumerate(backend.TIPOS_PATRIMONIO, start=1):
        assert backend.registrar_patrimonio(f"PAT-{indice:03d}", tipo, "Consultório", "UBS Teste", f"Fabricante {indice}")

    assert len(estado["df"]) == 6
    assert set(estado["df"]["Tipo de Patrimônio"]) == set(backend.TIPOS_PATRIMONIO)
    assert set(estado["df"]["Nº de Patrimônio"]) == {f"PAT-{i:03d}" for i in range(1, 7)}


def test_registro_com_numero_explicito_sem_codigo(monkeypatch):
    estado = {"df": pd.DataFrame(columns=backend.COLUNAS_INVENTARIO)}
    monkeypatch.setattr(backend, "carregar_dados_excel", lambda unidade: (estado["df"].copy(), "teste"))
    monkeypatch.setattr(backend, "salvar_no_excel", lambda df, unidade: estado.__setitem__("df", df.copy()) or True)

    assert backend.registrar_patrimonio("", "Mouse", "Recepção", "UBS Teste", "Dell", "PAT-EXPLICITO")
    assert estado["df"].iloc[0]["Nº de Patrimônio"] == "PAT-EXPLICITO"


def test_cadastro_legacy_da_tela_e_convertido_para_schema_atual(monkeypatch):
    estado = {"df": pd.DataFrame(columns=backend.COLUNAS_INVENTARIO)}
    monkeypatch.setattr(backend, "conectar_google_sheets", lambda: None)
    monkeypatch.setattr(backend.st, "error", lambda mensagem: None)

    # Simula exatamente o formato legado produzido pela função de cadastro da tela:
    # Setor + coluna do tipo + coluna Fabricante do tipo.
    legado = pd.DataFrame([{"Setor": "Farmacia", "CPU": "CPU-UI-001", "Fabricante CPU": "Dell"}])
    assert backend._normalizar_legacy_dataframe(legado).to_dict("records") == [{
        "Setor": "Farmacia",
        "Tipo de Patrimônio": "CPU",
        "Nº de Patrimônio": "CPU-UI-001",
        "Fabricante": "Dell",
        "Data Cadastro": "",
    }]


class _FakeWorksheet:
    def __init__(self):
        self.row_count = 100
        self.rows = []

    def get_all_values(self):
        return [list(row) for row in self.rows]

    def batch_clear(self, _ranges):
        self.rows = []

    def update(self, values, range_name="A1"):
        self.rows = [list(row) for row in values]


class _FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}

    def worksheet(self, name):
        if name not in self.sheets:
            import gspread
            raise gspread.exceptions.WorksheetNotFound
        return self.sheets[name]

    def add_worksheet(self, title, rows, cols):
        sheet = _FakeWorksheet()
        self.sheets[title] = sheet
        return sheet


def test_salvar_no_google_confirma_leitura_de_volta(monkeypatch, tmp_path):
    planilha = _FakeSpreadsheet()
    monkeypatch.setattr(backend, "conectar_google_sheets", lambda: planilha)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(backend.st, "error", lambda mensagem: None)

    df = pd.DataFrame([{
        "Setor": "Farmacia",
        "Tipo de Patrimônio": "Monitores",
        "Nº de Patrimônio": "MON-001",
        "Fabricante": "Samsung",
        "Data Cadastro": "2026-09-09 12:00:00",
    }], columns=backend.COLUNAS_INVENTARIO)

    assert backend.salvar_no_excel(df, "UBS Teste") is True
    assert planilha.sheets["UBS Teste"].rows == [backend.COLUNAS_INVENTARIO, ["Farmacia", "Monitores", "MON-001", "Samsung", "2026-09-09 12:00:00"]]


def test_falha_google_nao_vira_falso_sucesso_por_backup_local(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "conectar_google_sheets", lambda: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(backend.st, "error", lambda mensagem: None)

    df = pd.DataFrame([{
        "Setor": "Farmacia",
        "Tipo de Patrimônio": "CPU",
        "Nº de Patrimônio": "CPU-001",
        "Fabricante": "Dell",
        "Data Cadastro": "2026-09-09 12:00:00",
    }], columns=backend.COLUNAS_INVENTARIO)

    assert backend.salvar_no_excel(df, "UBS Falha") is False
    assert (tmp_path / "Inventario_UBS_Falha.xlsx").exists()


def test_exclusao_de_setor_remove_todas_as_linhas():
    df = pd.DataFrame(
        [
            {"Setor": "Farmacia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-1"},
            {"Setor": "Farmacia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "MON-1"},
            {"Setor": "Recepção", "Tipo de Patrimônio": "Mouse", "Nº de Patrimônio": "M-1"},
        ]
    )
    novo, alterado = backend._aplicar_exclusao_setor(df, "farmacia")

    assert alterado is True
    assert len(novo) == 1
    assert novo.iloc[0]["Setor"] == "Recepção"


def test_exclusao_por_numero_eh_especifica_do_setor():
    df = pd.DataFrame(
        [
            {"Setor": "Farmacia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "ABC"},
            {"Setor": "Recepção", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "ABC"},
        ]
    )
    novo, alterado = backend._aplicar_exclusao_patrimonio(df, "Farmacia", "Nº de Patrimônio")

    assert alterado is True
    assert len(novo) == 1
    assert novo.iloc[0]["Setor"] == "Recepção"


def test_data_hora_cadastro_brasilia(monkeypatch):
    estado = {"df": pd.DataFrame(columns=backend.COLUNAS_INVENTARIO)}
    monkeypatch.setattr(backend, "carregar_dados_excel", lambda unidade: (estado["df"].copy(), "teste"))
    monkeypatch.setattr(backend, "salvar_no_excel", lambda df, unidade: estado.__setitem__("df", df.copy()) or True)
    assert backend.registrar_patrimonio("PAT-DATA-001", "CPU", "Farmacia", "UBS Teste", "Dell")
    valor = estado["df"].iloc[-1]["Data Cadastro"]
    dt = backend.datetime.strptime(valor, "%Y-%m-%d %H:%M:%S").replace(tzinfo=backend.FUSO_HORARIO_APLICACAO)
    agora = backend._agora_brasilia()
    assert valor
    assert len(valor) == 19
    assert abs((agora - dt).total_seconds()) < 10


def test_cadastro_nao_reintroduz_colunas_removidas(monkeypatch):
    estado = {"df": pd.DataFrame(columns=backend.COLUNAS_INVENTARIO)}
    monkeypatch.setattr(backend, "carregar_dados_excel", lambda unidade: (estado["df"].copy(), "teste"))
    monkeypatch.setattr(backend, "salvar_no_excel", lambda df, unidade: estado.__setitem__("df", df.copy()) or True)
    assert backend.registrar_patrimonio("PAT-SCHEMA-001", "Monitores", "Farmacia", "UBS Teste", "HP")
    assert list(estado["df"].columns) == backend.COLUNAS_INVENTARIO
    assert not any(c in estado["df"].columns for c in ("Código de Barras", "Origem", "Status"))
