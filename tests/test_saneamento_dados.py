import pandas as pd

import Tabela_de_dados_Inventario_7_2 as backend
from saneamento_dados import preparar_saneamento


COLUNAS = backend.COLUNAS_INVENTARIO


def test_saneamento_remove_linha_incompleta_sem_inventar_dados():
    df = pd.DataFrame([
        {"Setor": "Consultório", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-001", "Fabricante": "Dell", "Data Cadastro": ""},
        {"Setor": "Consultório", "Tipo de Patrimônio": "", "Nº de Patrimônio": "", "Fabricante": "", "Data Cadastro": ""},
    ])
    resultado, relatorio = preparar_saneamento(df, "URS Serra Sede")
    assert len(resultado) == 1
    assert resultado.iloc[0]["Nº de Patrimônio"] == "CPU-001"
    assert relatorio.linhas_lidas == 2
    assert relatorio.linhas_removidas == 1
    assert relatorio.alterado is True


def test_saneamento_normaliza_alias_de_tipo_e_preserva_schema():
    df = pd.DataFrame([
        {"Setor": "Farmacia", "Tipo de Patrimônio": "cpu", "Nº de Patrimônio": "001", "Fabricante": "Lenovo", "Data Cadastro": ""},
    ])
    resultado, relatorio = preparar_saneamento(df, "UBS Teste")
    assert list(resultado.columns) == COLUNAS
    assert resultado.iloc[0]["Tipo de Patrimônio"] == "CPU"
    assert relatorio.linhas_resultado == 1


def test_saneamento_remove_duplicata_preservando_primeira():
    df = pd.DataFrame([
        {"Setor": "Recepção", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "MON-001", "Fabricante": "Dell", "Data Cadastro": "primeira"},
        {"Setor": "Recepção", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "MON-001", "Fabricante": "HP", "Data Cadastro": "segunda"},
    ])
    resultado, relatorio = preparar_saneamento(df, "UBS Teste")
    assert len(resultado) == 1
    assert resultado.iloc[0]["Fabricante"] == "Dell"
    assert relatorio.duplicatas_removidas == 1


def test_saneamento_nao_remove_numero_igual_em_setores_diferentes():
    df = pd.DataFrame([
        {"Setor": "Farmacia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "PAT-001", "Fabricante": "Dell", "Data Cadastro": ""},
        {"Setor": "Recepção", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "PAT-001", "Fabricante": "Dell", "Data Cadastro": ""},
    ])
    resultado, relatorio = preparar_saneamento(df, "UBS Teste")
    assert len(resultado) == 2
    assert relatorio.duplicatas_removidas == 0


def test_saneamento_remove_colunas_obsoletas():
    df = pd.DataFrame([
        {"Setor": "Odontologia", "Tipo de Patrimônio": "Mouse", "Nº de Patrimônio": "M-01", "Fabricante": "Logitech", "Data Cadastro": "", "Código de Barras": "123", "Origem": "scanner", "Status": "Ativo"},
    ])
    resultado, _ = preparar_saneamento(df, "UBS Teste")
    assert list(resultado.columns) == COLUNAS
    assert "Código de Barras" not in resultado.columns
    assert "Origem" not in resultado.columns
    assert "Status" not in resultado.columns
