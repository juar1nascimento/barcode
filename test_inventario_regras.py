import pandas as pd

from inventario_regras import (
    lista_unica_ordenada,
    normalizar_dataframe_inventario,
    normalizar_fabricante,
    normalizar_setor,
    ordenar_inventario,
    setores_menu,
    texto_menu_proibido,
    tipos_patrimonio_menu,
)
from Tabela_de_dados_Inventario_7_2 import _aplicar_exclusao_patrimonio, _aplicar_exclusao_setor


def test_setores_menu_eh_unico_ordenado_e_sem_cabecalhos():
    setores = setores_menu()
    assert setores == sorted(set(setores), key=str.casefold)
    assert "Farmacia" not in setores
    assert "Gerencia" not in setores
    assert "Sala de curativo" not in setores
    assert "Local / Setor" not in setores
    assert "Fabricante Monitor" not in setores


def test_setores_historicos_distintos_sao_preservados():
    setores = setores_menu()
    assert "Consultório 2" in setores
    assert "Consultório 4 - odontologia" in setores
    assert "Consultório 5 - Enfermaria" in setores
    assert "Consultório 6 - Clinico" in setores
    assert "Consultório 7 - odontologia" in setores
    assert "Sala dos Agentes de Saúde" in setores
    assert "Triagem" in setores


def test_tipos_menu_nao_contem_artefatos():
    tipos = tipos_patrimonio_menu()
    assert tipos == sorted(set(tipos), key=str.casefold)
    assert "Fabricante CPU" not in tipos
    assert "Local/Setor" not in tipos
    assert "Nobreak" not in tipos
    assert "Outros Dispositivos" in tipos


def test_lista_unica_ordenada_remove_duplicatas_case_insensitive():
    valores = ["HP", "hp", " Dell ", "dell", "", "Fabricante CPU", "Lenovo"]
    assert lista_unica_ordenada(valores, normalizar_fabricante) == ["Dell", "HP", "Lenovo"]


def test_normalizacoes_preservam_setores_distintos():
    assert normalizar_setor("Farmacia") == "Farmácia"
    assert normalizar_setor("Gerencia") == "Gerência"
    assert normalizar_setor("Sala de curativo") == "Sala de Curativo"
    assert normalizar_setor("Consultório 4 - odontologia") == "Consultório 4 - odontologia"
    assert normalizar_setor("Consultório 7 - odontologia") == "Consultório 7 - odontologia"


def test_textos_proibidos():
    assert texto_menu_proibido("Local / Setor")
    assert texto_menu_proibido("Local/Setor")
    assert texto_menu_proibido("Fabricante Monitor")
    assert texto_menu_proibido("Fabricante Computador")
    assert texto_menu_proibido("Fabricante CPU")
    assert not texto_menu_proibido("Dell")


def test_normalizar_dataframe_e_ordenar_nao_apagam_registros():
    df = pd.DataFrame([
        {"Setor": "Farmacia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "20", "Fabricante": "hp"},
        {"Setor": "Almoxarifado", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "10", "Fabricante": "dell"},
        {"Setor": "Farmácia", "Tipo de Patrimônio": "Teclado", "Nº de Patrimônio": "11", "Fabricante": "Lenovo"},
    ])
    normalizado = normalizar_dataframe_inventario(df)
    ordenado = ordenar_inventario(normalizado)
    assert len(ordenado) == 3
    assert ordenado.iloc[0]["Setor"] == "Almoxarifado"
    assert ordenado.iloc[1]["Fabricante"] == "HP"
    assert ordenado.iloc[2]["Fabricante"] == "Lenovo"


def _df_teste_exclusao():
    return pd.DataFrame([
        {"Setor": "Farmacia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "MON-001", "Código de Barras": "111", "Fabricante": "hp", "Data Cadastro": "", "Origem": "", "Status": "Ativo"},
        {"Setor": "Farmácia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "MON-002", "Código de Barras": "222", "Fabricante": "Dell", "Data Cadastro": "", "Origem": "", "Status": "Ativo"},
        {"Setor": "Farmácia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-001", "Código de Barras": "333", "Fabricante": "Lenovo", "Data Cadastro": "", "Origem": "", "Status": "Ativo"},
        {"Setor": "Almoxarifado", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "MON-003", "Código de Barras": "444", "Fabricante": "Dell", "Data Cadastro": "", "Origem": "", "Status": "Ativo"},
    ])


def test_exclusao_patrimonio_remove_somente_um_registro_do_setor():
    df = _df_teste_exclusao()
    novo, alterado = _aplicar_exclusao_patrimonio(df, "Farmácia", "Código de Barras")
    assert alterado is True
    assert len(novo) == 3
    assert "333" not in novo["Código de Barras"].tolist()
    assert "111" in novo["Código de Barras"].tolist()
    assert "222" in novo["Código de Barras"].tolist()
    assert "444" in novo["Código de Barras"].tolist()


def test_exclusao_patrimonio_nao_apaga_outro_setor():
    df = _df_teste_exclusao()
    novo, alterado = _aplicar_exclusao_patrimonio(df, "Farmacia", "Tipo de Patrimônio")
    assert alterado is True
    assert "444" in novo["Código de Barras"].tolist()


def test_exclusao_setor_remove_todos_os_registros_do_setor_normalizado():
    df = _df_teste_exclusao()
    novo, alterado = _aplicar_exclusao_setor(df, "Farmacia")
    assert alterado is True
    assert len(novo) == 1
    assert novo.iloc[0]["Código de Barras"] == "444"
