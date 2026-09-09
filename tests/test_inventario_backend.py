import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Tabela_de_dados_Inventario_7_2 as backend

TIPOS = backend.TIPOS_PATRIMONIO
COLUNAS = backend.COLUNAS_INVENTARIO


def _estado_vazio():
    return {"df": pd.DataFrame(columns=COLUNAS)}


def _mock_persistencia(monkeypatch, estado):
    monkeypatch.setattr(backend, "carregar_dados_excel", lambda unidade: (estado["df"].copy(), "teste"))
    monkeypatch.setattr(backend, "salvar_no_excel", lambda df, unidade: estado.__setitem__("df", df.copy()) or True)


def test_schema_e_tipo_patrimonio():
    assert COLUNAS == ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Fabricante", "Data Cadastro"]
    assert "Código de Barras" not in COLUNAS
    assert "Origem" not in COLUNAS
    assert "Status" not in COLUNAS
    assert TIPOS == ("CPU", "Monitores", "Teclado", "Mouse", "Imprenssoras", "Outros Dispositivos")


def test_lista_de_setores_oficial():
    assert backend.SETORES_PADRAO == [
        "Consultório", "Almoxarifado", "Farmacia", "Sala de Preparo", "Sala de Vacina",
        "Sala de curativo", "Gerencia", "Administração", "Odontologia", "Recepção", "Outro Setor",
    ]


def test_normalizacao_legacy_converte_varios_tipos():
    df = pd.DataFrame([
        {"Setor": "Farmacia", "Computador": "PAT-001", "Fabricante Computador": "Dell", "Monitor": "MON-001"},
        {"Setor": "Farmacia", "Monitor": "MON-002", "Fabricante Monitor": "HP"},
    ])
    normalizado = backend._normalizar_legacy_dataframe(df)
    assert len(normalizado) == 3
    assert set(normalizado["Tipo de Patrimônio"]) == {"CPU", "Monitores"}
    assert set(normalizado["Nº de Patrimônio"]) == {"PAT-001", "MON-001", "MON-002"}
    assert list(normalizado.columns) == COLUNAS


def test_normalizacao_remove_valores_vazios_e_preserva_numero():
    df = pd.DataFrame([{
        "Setor": "  Recepção  ", "Tipo de Patrimônio": "Mouse", "Nº de Patrimônio": " 0007 ",
        "Fabricante": " Logitech ", "Data Cadastro": "2026-09-09 10:00:00", "Status": "Ativo",
    }])
    normalizado = backend._normalizar_legacy_dataframe(df)
    assert normalizado.iloc[0]["Nº de Patrimônio"] == "0007"
    assert normalizado.iloc[0]["Fabricante"] == "Logitech"
    assert list(normalizado.columns) == COLUNAS


def test_registro_usa_codigo_lido_como_numero_de_patrimonio(monkeypatch):
    estado = _estado_vazio()
    avisos = []
    _mock_persistencia(monkeypatch, estado)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: avisos.append(mensagem))
    assert backend.registrar_patrimonio("789000000001", "Monitores", "Farmacia", "UBS Teste", "Dell")
    assert backend.registrar_patrimonio("789000000002", "Monitores", "Farmacia", "UBS Teste", "HP")
    assert len(estado["df"]) == 2
    assert set(estado["df"]["Nº de Patrimônio"]) == {"789000000001", "789000000002"}
    assert not any(c in estado["df"].columns for c in ("Código de Barras", "Origem", "Status"))
    assert avisos == []


def test_registro_bloqueia_numero_duplicado_com_espacos_e_maiusculas(monkeypatch):
    estado = {"df": pd.DataFrame([{
        "Setor": "Farmacia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "abc 123",
        "Fabricante": "Dell", "Data Cadastro": "",
    }], columns=COLUNAS)}
    avisos = []
    _mock_persistencia(monkeypatch, estado)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: avisos.append(mensagem))
    assert not backend.registrar_patrimonio("  ABC   123  ", "Monitores", "Farmacia", "UBS Teste", "HP")
    assert len(estado["df"]) == 1
    assert avisos


def test_mesmo_numero_e_bloqueado_em_outro_setor_da_mesma_unidade(monkeypatch):
    estado = {"df": pd.DataFrame([{
        "Setor": "Farmacia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "PAT-001",
        "Fabricante": "Dell", "Data Cadastro": "",
    }], columns=COLUNAS)}
    _mock_persistencia(monkeypatch, estado)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: None)
    assert not backend.registrar_patrimonio("PAT-001", "CPU", "Recepção", "UBS Teste", "HP")
    assert len(estado["df"]) == 1


def test_mesmo_numero_pode_existir_em_unidades_diferentes(monkeypatch):
    estados = {"UBS A": pd.DataFrame(columns=COLUNAS), "UBS B": pd.DataFrame(columns=COLUNAS)}
    monkeypatch.setattr(backend, "carregar_dados_excel", lambda unidade: (estados[unidade].copy(), "teste"))
    monkeypatch.setattr(backend, "salvar_no_excel", lambda df, unidade: estados.__setitem__(unidade, df.copy()) or True)
    assert backend.registrar_patrimonio("PAT-001", "CPU", "Farmacia", "UBS A", "Dell")
    assert backend.registrar_patrimonio("PAT-001", "CPU", "Farmacia", "UBS B", "Dell")
    assert len(estados["UBS A"]) == 1 and len(estados["UBS B"]) == 1


def test_todos_os_seis_tipos_podem_ser_cadastrados(monkeypatch):
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    for indice, tipo in enumerate(TIPOS, start=1):
        assert backend.registrar_patrimonio(f"PAT-{indice:03d}", tipo, "Consultório", "UBS Teste", f"Fabricante {indice}")
    assert len(estado["df"]) == 6
    assert set(estado["df"]["Tipo de Patrimônio"]) == set(TIPOS)


def test_aliases_de_tipo_legado_sao_aceitos_sem_reintroduzir_tipo_antigo(monkeypatch):
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    for indice, alias in enumerate(["computador", "monitor", "teclado", "mouse", "impressora", "imprenssoras"], start=1):
        assert backend.registrar_patrimonio(f"ALIAS-{indice}", alias, "Almoxarifado", "UBS Teste", "Marca")
    assert list(estado["df"]["Tipo de Patrimônio"]) == ["CPU", "Monitores", "Teclado", "Mouse", "Imprenssoras", "Imprenssoras"]


def test_tipo_invalido_nao_vira_outros_dispositivos(monkeypatch):
    estado = _estado_vazio()
    avisos = []
    _mock_persistencia(monkeypatch, estado)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: avisos.append(mensagem))
    assert not backend.registrar_patrimonio("PAT-INVALIDO", "Celular", "Farmacia", "UBS Teste", "Apple")
    assert estado["df"].empty
    assert avisos


def test_registro_com_numero_explicito_sem_codigo(monkeypatch):
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    assert backend.registrar_patrimonio("", "Mouse", "Recepção", "UBS Teste", "Dell", "PAT-EXPLICITO")
    assert estado["df"].iloc[0]["Nº de Patrimônio"] == "PAT-EXPLICITO"


def test_numero_explicito_tem_precedencia_sobre_codigo_lido(monkeypatch):
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    assert backend.registrar_patrimonio("CODIGO-SCANNER", "CPU", "Farmacia", "UBS Teste", "Dell", "PAT-REAL-001")
    assert estado["df"].iloc[0]["Nº de Patrimônio"] == "PAT-REAL-001"


def test_fabricante_e_opcional(monkeypatch):
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    assert backend.registrar_patrimonio("PAT-SEM-MARCA", "Outros Dispositivos", "Outro Setor", "UBS Teste")
    assert estado["df"].iloc[0]["Fabricante"] == ""


def test_todos_os_setores_oficiais_e_outro_setor_customizado(monkeypatch):
    for indice, setor in enumerate(backend.SETORES_PADRAO, start=1):
        estado = _estado_vazio()
        _mock_persistencia(monkeypatch, estado)
        assert backend.registrar_patrimonio(f"SETOR-{indice}", "Mouse", setor, "UBS Teste", "Marca")
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    assert backend.registrar_patrimonio("SETOR-CUSTOM", "Mouse", "Sala Técnica de TI", "UBS Teste", "Marca")
    assert estado["df"].iloc[0]["Setor"] == "Sala Técnica de TI"


def test_cadastros_invalidos_sao_rejeitados(monkeypatch):
    estado = _estado_vazio()
    avisos = []
    _mock_persistencia(monkeypatch, estado)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: avisos.append(mensagem))
    casos = [
        ("", "CPU", "Farmacia", "UBS Teste"),
        ("PAT-1", "", "Farmacia", "UBS Teste"),
        ("PAT-2", "CPU", "", "UBS Teste"),
        ("PAT-3", "CPU", "Farmacia", ""),
        ("PAT-4", "CPU", "Selecione um setor...", "UBS Teste"),
        ("PAT-5", "CPU", "Farmacia", "Selecione uma UBS..."),
    ]
    for codigo, tipo, setor, unidade in casos:
        assert not backend.registrar_patrimonio(codigo, tipo, setor, unidade, "Dell")
    assert estado["df"].empty
    assert len(avisos) == len(casos)


def test_normalizacao_de_numero_numerico_remove_apenas_sufixo_decimal_artificial():
    assert backend._valor_texto(123.0) == "123"
    assert backend._valor_texto("00123") == "00123"
    assert backend._valor_texto("-5.0") == "-5"


def test_validacao_de_cadastro_retorna_motivos_claros():
    assert backend.validar_cadastro_patrimonio("CPU", "Farmacia", "UBS Teste", "PAT-1") == (True, "")
    ok, msg = backend.validar_cadastro_patrimonio("Celular", "Farmacia", "UBS Teste", "PAT-1")
    assert not ok and "tipo" in msg.lower()
    ok, msg = backend.validar_cadastro_patrimonio("CPU", "Farmacia", "UBS Teste", "")
    assert not ok and "número" in msg.lower()


def test_cadastro_legacy_da_tela_e_convertido_para_schema_atual():
    legado = pd.DataFrame([{"Setor": "Farmacia", "CPU": "CPU-UI-001", "Fabricante CPU": "Dell"}])
    assert backend._normalizar_legacy_dataframe(legado).to_dict("records") == [{
        "Setor": "Farmacia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-UI-001",
        "Fabricante": "Dell", "Data Cadastro": "",
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

    def append_rows(self, values, value_input_option="RAW", insert_data_option=None):
        self.rows.extend([list(row) for row in values])


class _FakeWorksheetMismatch(_FakeWorksheet):
    def get_all_values(self):
        rows = super().get_all_values()
        if len(rows) > 1:
            rows[1][2] = "DADO-DIFERENTE"
        return rows


class _FakeSpreadsheet:
    def __init__(self, worksheet_factory=_FakeWorksheet):
        self.sheets = {}
        self.worksheet_factory = worksheet_factory

    def worksheet(self, name):
        if name not in self.sheets:
            import gspread
            raise gspread.exceptions.WorksheetNotFound
        return self.sheets[name]

    def add_worksheet(self, title, rows, cols):
        sheet = self.worksheet_factory()
        self.sheets[title] = sheet
        return sheet


def _df_exemplo():
    return pd.DataFrame([{
        "Setor": "Farmacia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "MON-001",
        "Fabricante": "Samsung", "Data Cadastro": "2026-09-09 12:00:00",
    }], columns=COLUNAS)


def test_salvar_no_google_confirma_leitura_de_volta(monkeypatch, tmp_path):
    planilha = _FakeSpreadsheet()
    monkeypatch.setattr(backend, "conectar_google_sheets", lambda: planilha)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(backend.st, "error", lambda mensagem: None)
    assert backend.salvar_no_excel(_df_exemplo(), "UBS Teste") is True
    assert planilha.sheets["UBS Teste"].rows == [COLUNAS, ["Farmacia", "Monitores", "MON-001", "Samsung", "2026-09-09 12:00:00"]]


def test_google_com_leitura_de_confirmacao_diferente_eh_falha(monkeypatch, tmp_path):
    planilha = _FakeSpreadsheet(_FakeWorksheetMismatch)
    erros = []
    monkeypatch.setattr(backend, "conectar_google_sheets", lambda: planilha)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(backend.st, "error", lambda mensagem: erros.append(mensagem))
    assert backend.salvar_no_excel(_df_exemplo(), "UBS Teste") is False
    assert erros


def test_falha_google_nao_vira_falso_sucesso_por_backup_local(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "conectar_google_sheets", lambda: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(backend.st, "error", lambda mensagem: None)
    assert backend.salvar_no_excel(_df_exemplo(), "UBS Falha") is False
    assert (tmp_path / "Inventario_UBS_Falha.xlsx").exists()


def test_exclusao_de_setor_remove_todas_as_linhas():
    df = pd.DataFrame([
        {"Setor": "Farmacia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-1"},
        {"Setor": "Farmacia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "MON-1"},
        {"Setor": "Recepção", "Tipo de Patrimônio": "Mouse", "Nº de Patrimônio": "M-1"},
    ])
    novo, alterado = backend._aplicar_exclusao_setor(df, "farmacia")
    assert alterado is True
    assert len(novo) == 1
    assert novo.iloc[0]["Setor"] == "Recepção"


def test_exclusao_por_numero_eh_especifica_do_setor():
    df = pd.DataFrame([
        {"Setor": "Farmacia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "ABC"},
        {"Setor": "Recepção", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "ABC"},
    ])
    novo, alterado = backend._aplicar_exclusao_patrimonio(df, "Farmacia", "Nº de Patrimônio")
    assert alterado is True
    assert len(novo) == 1
    assert novo.iloc[0]["Setor"] == "Recepção"


def test_data_hora_cadastro_brasilia(monkeypatch):
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    assert backend.registrar_patrimonio("PAT-DATA-001", "CPU", "Farmacia", "UBS Teste", "Dell")
    valor = estado["df"].iloc[-1]["Data Cadastro"]
    dt = backend.datetime.strptime(valor, "%Y-%m-%d %H:%M:%S").replace(tzinfo=backend.FUSO_HORARIO_APLICACAO)
    agora = backend._agora_brasilia()
    assert valor and len(valor) == 19
    assert abs((agora - dt).total_seconds()) < 10


def test_cadastro_nao_reintroduz_colunas_removidas(monkeypatch):
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    assert backend.registrar_patrimonio("PAT-SCHEMA-001", "Monitores", "Farmacia", "UBS Teste", "HP")
    assert list(estado["df"].columns) == COLUNAS
    assert not any(c in estado["df"].columns for c in ("Código de Barras", "Origem", "Status"))



def test_carga_em_massa_sem_gravacao_parcial(monkeypatch):
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    registros = [
        {"tipo_patrimonio": "CPU", "setor": "Farmacia", "numero_patrimonio": f"LOTE-{i:03d}", "fabricante": "Dell"}
        for i in range(1, 101)
    ]
    ok, erros = backend.registrar_patrimonios_em_lote(registros, "UBS Teste")
    assert ok and erros == []
    assert len(estado["df"]) == 100
    assert list(estado["df"]["Nº de Patrimônio"])[0] == "LOTE-001"
    assert list(estado["df"]["Nº de Patrimônio"])[-1] == "LOTE-100"


def test_carga_em_massa_com_duplicidade_nao_grava_parcialmente(monkeypatch):
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    registros = [
        {"tipo_patrimonio": "CPU", "setor": "Farmacia", "numero_patrimonio": "LOTE-001"},
        {"tipo_patrimonio": "Monitor", "setor": "Farmacia", "numero_patrimonio": "LOTE-002"},
        {"tipo_patrimonio": "CPU", "setor": "Farmacia", "numero_patrimonio": " lote-001 "},
    ]
    ok, erros = backend.registrar_patrimonios_em_lote(registros, "UBS Teste")
    assert not ok
    assert erros
    assert estado["df"].empty


def test_carga_em_massa_rejeita_lote_maior_que_limite(monkeypatch):
    estado = _estado_vazio()
    _mock_persistencia(monkeypatch, estado)
    registros = [
        {"tipo_patrimonio": "CPU", "setor": "Farmacia", "numero_patrimonio": f"MAX-{i}"}
        for i in range(1001)
    ]
    ok, erros = backend.registrar_patrimonios_em_lote(registros, "UBS Teste")
    assert not ok and erros
    assert estado["df"].empty


def test_interface_delega_cadastro_ao_backend(monkeypatch):
    import sistema_inventario as ui
    chamadas = []
    monkeypatch.setattr(ui, "registrar_patrimonio", lambda *args: chamadas.append(args) or True)
    assert ui.adicionar_e_salvar("PAT-UI-001", "CPU", "Farmacia", "UBS Teste", "Dell")
    assert chamadas == [("PAT-UI-001", "CPU", "Farmacia", "UBS Teste", "Dell")]


def test_cadastro_normal_anexa_sem_limpar_aba(monkeypatch, tmp_path):
    planilha = _FakeSpreadsheet()
    aba = planilha.add_worksheet(title="UBS Teste", rows=100, cols=len(COLUNAS))
    aba.update(values=[COLUNAS, ["Farmacia", "CPU", "EXISTENTE", "Dell", "2026-09-09 10:00:00"]], range_name="A1")
    monkeypatch.setattr(backend, "conectar_google_sheets", lambda: planilha)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(backend.st, "error", lambda mensagem: None)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: None)
    backend.carregar_dados_excel.clear()
    assert backend.registrar_patrimonio("NOVO-001", "Monitores", "Consultório", "UBS Teste", "HP") is True
    rows = planilha.sheets["UBS Teste"].rows
    assert len(rows) == 3
    assert rows[1][2] == "EXISTENTE"
    assert rows[2][2] == "NOVO-001"


def test_carga_em_lote_anexa_apenas_novas_linhas(monkeypatch, tmp_path):
    planilha = _FakeSpreadsheet()
    aba = planilha.add_worksheet(title="UBS Teste", rows=100, cols=len(COLUNAS))
    aba.update(values=[COLUNAS, ["Farmacia", "CPU", "BASE-001", "Dell", "2026-09-09 10:00:00"]], range_name="A1")
    monkeypatch.setattr(backend, "conectar_google_sheets", lambda: planilha)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(backend.st, "error", lambda mensagem: None)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: None)
    backend.carregar_dados_excel.clear()
    registros = [
        {"tipo_patrimonio": "CPU", "setor": "Farmacia", "numero_patrimonio": "LOTE-001", "fabricante": "Dell"},
        {"tipo_patrimonio": "Mouse", "setor": "Farmacia", "numero_patrimonio": "LOTE-002", "fabricante": "HP"},
    ]
    ok, erros = backend.registrar_patrimonios_em_lote(registros, "UBS Teste")
    assert ok and erros == []
    rows = planilha.sheets["UBS Teste"].rows
    assert [r[2] for r in rows[1:]] == ["BASE-001", "LOTE-001", "LOTE-002"]


def test_cadastro_repetido_apos_append_e_idempotente(monkeypatch, tmp_path):
    planilha = _FakeSpreadsheet()
    aba = planilha.add_worksheet(title="UBS Teste", rows=100, cols=len(COLUNAS))
    aba.update(values=[COLUNAS, ["Farmacia", "CPU", "REPETIDO-001", "Dell", "2026-09-09 10:00:00"]], range_name="A1")
    monkeypatch.setattr(backend, "conectar_google_sheets", lambda: planilha)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(backend.st, "error", lambda mensagem: None)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: None)
    backend.carregar_dados_excel.clear()
    assert backend.registrar_patrimonio("REPETIDO-001", "CPU", "Farmacia", "UBS Teste", "Dell") is False
    rows = planilha.sheets["UBS Teste"].rows
    assert [r[2] for r in rows[1:]] == ["REPETIDO-001"]
