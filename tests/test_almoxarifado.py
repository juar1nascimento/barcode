import postgresql_persistencia as pg
from Tabela_de_dados_Inventario_7_2 import LISTA_ALMOXARIFADO_PADRAO, UNIDADES_PADRAO


def test_almoxarifado_faz_parte_das_unidades_padrao():
    assert LISTA_ALMOXARIFADO_PADRAO == ["Almoxarifado Central SESA"]
    assert "Almoxarifado Central SESA" in UNIDADES_PADRAO


def test_almoxarifado_e_classificado_como_almox():
    assert pg._tipo_unidade("Almoxarifado Central SESA") == "ALMOX"
    assert pg._tipo_unidade(" almoxarifado central sesa ") == "ALMOX"


def test_ubs_e_urs_continuam_com_classificacao_original():
    assert pg._tipo_unidade("UBS André Carloni") == "UBS"
    assert pg._tipo_unidade("URS Serra Sede") == "URS"
