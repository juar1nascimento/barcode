import pandas as pd

from auditoria_integridade_google import normalizar_data_hora, normalizar_dataframe_google


def test_normalizar_data_hora_iso_para_brasileiro():
    assert normalizar_data_hora("2026-09-09 18:30:45") == "09-09-2026 18:30:45"


def test_normalizar_data_hora_preserva_formato_brasileiro():
    assert normalizar_data_hora("09-09-2026 18:30:45") == "09-09-2026 18:30:45"


def test_normalizar_dataframe_corrige_coluna_data():
    df = pd.DataFrame([{
        "Setor": "Farmacia",
        "Tipo de Patrimônio": "CPU",
        "Nº de Patrimônio": "PAT-8",
        "Fabricante": "Dell",
        "Data Cadastro": "2026-09-09 18:30:45",
    }])
    out = normalizar_dataframe_google(df)
    assert out.iloc[0]["Data Cadastro"] == "09-09-2026 18:30:45"
