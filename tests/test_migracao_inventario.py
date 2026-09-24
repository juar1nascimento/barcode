import pandas as pd

from Tabela_de_dados_Inventario_7_2 import _classificar_migracao_legacy


def test_classificacao_migracao_identifica_candidatos_e_existentes():
    df = pd.DataFrame([
        {"Setor": "Almoxarifado", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "100", "Fabricante": "Dell"},
        {"Setor": "Almoxarifado", "Tipo de Patrimônio": "Monitor", "Nº de Patrimônio": "200", "Fabricante": "LG"},
    ])
    pg = {
        "100": {"numero": "100", "tipo": "CPU", "setor": "Almoxarifado", "fabricante": "Dell"}
    }
    resultado = _classificar_migracao_legacy(df, pg)
    assert len(resultado["ja_existentes_pg"]) == 1
    assert len(resultado["validos_para_migracao"]) == 1


def test_classificacao_detecta_duplicidade_na_planilha():
    df = pd.DataFrame([
        {"Setor": "Almoxarifado", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "100", "Fabricante": ""},
        {"Setor": "Almoxarifado", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "100", "Fabricante": ""},
    ])
    resultado = _classificar_migracao_legacy(df, {})
    assert len(resultado["validos_para_migracao"]) == 1
    assert len(resultado["duplicados_planilha"]) == 1


def test_classificacao_detecta_dados_invalidos():
    df = pd.DataFrame([
        {"Setor": "", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "100", "Fabricante": ""},
        {"Setor": "Almoxarifado", "Tipo de Patrimônio": "", "Nº de Patrimônio": "200", "Fabricante": ""},
    ])
    resultado = _classificar_migracao_legacy(df, {})
    assert len(resultado["invalidos"]) == 2


def test_classificacao_detecta_divergencia_com_postgresql():
    df = pd.DataFrame([
        {"Setor": "Almoxarifado", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "100", "Fabricante": "LG"},
    ])
    pg = {
        "100": {"numero": "100", "tipo": "CPU", "setor": "Almoxarifado", "fabricante": "Dell"}
    }
    resultado = _classificar_migracao_legacy(df, pg)
    assert len(resultado["divergentes_pg"]) == 1
    assert "fabricante" in resultado["divergentes_pg"][0]["campos"]
