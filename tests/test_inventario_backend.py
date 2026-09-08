import pandas as pd

import Tabela_de_dados_Inventario_7_2 as backend


def test_schema_and_tipo_patrimonio():
    assert backend.COLUNAS_INVENTARIO == [
        "Setor",
        "Tipo de Patrimônio",
        "Nº de Patrimônio",
        "Código de Barras",
        "Fabricante",
        "Data Cadastro",
        "Origem",
        "Status",
    ]
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


def test_registro_permite_varios_patrimonios_no_mesmo_setor(monkeypatch):
    estado = {"df": pd.DataFrame(columns=backend.COLUNAS_INVENTARIO)}
    avisos = []

    monkeypatch.setattr(backend, "carregar_dados_excel", lambda unidade: (estado["df"].copy(), "teste"))
    monkeypatch.setattr(backend, "salvar_no_excel", lambda df, unidade: estado.__setitem__("df", df.copy()) or True)
    monkeypatch.setattr(backend.st, "warning", lambda mensagem: avisos.append(mensagem))

    assert backend.registrar_patrimonio("789000000001", "Monitores", "Farmacia", "UBS Teste", "Dell")
    assert backend.registrar_patrimonio("789000000002", "Monitores", "Farmacia", "UBS Teste", "HP")

    assert len(estado["df"]) == 2
    assert set(estado["df"]["Código de Barras"]) == {"789000000001", "789000000002"}
    assert avisos == []


def test_registro_bloqueia_codigo_de_barras_duplicado(monkeypatch):
    estado = {
        "df": pd.DataFrame(
            [{
                "Setor": "Farmacia",
                "Tipo de Patrimônio": "Monitores",
                "Nº de Patrimônio": "PAT-001",
                "Código de Barras": "789000000001",
                "Fabricante": "Dell",
                "Data Cadastro": "",
                "Origem": "",
                "Status": "Ativo",
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
            {"Setor": "Farmacia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-1", "Código de Barras": "1"},
            {"Setor": "Farmacia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "MON-1", "Código de Barras": "2"},
            {"Setor": "Recepção", "Tipo de Patrimônio": "Mouse", "Nº de Patrimônio": "M-1", "Código de Barras": "3"},
        ]
    )
    novo, alterado = backend._aplicar_exclusao_setor(df, "farmacia")

    assert alterado is True
    assert len(novo) == 1
    assert novo.iloc[0]["Setor"] == "Recepção"


def test_exclusao_por_codigo_de_barras_eh_especifica_do_setor():
    df = pd.DataFrame(
        [
            {"Setor": "Farmacia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "M-1", "Código de Barras": "ABC"},
            {"Setor": "Recepção", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "M-2", "Código de Barras": "ABC"},
        ]
    )
    novo, alterado = backend._aplicar_exclusao_patrimonio(df, "Farmacia", "Código de Barras")

    assert alterado is True
    assert len(novo) == 1
    assert novo.iloc[0]["Setor"] == "Recepção"
