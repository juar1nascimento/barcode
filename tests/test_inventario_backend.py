import pandas as pd

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
