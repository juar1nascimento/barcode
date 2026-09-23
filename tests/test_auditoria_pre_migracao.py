def test_unidades_padrao_incluem_almoxarifado():
    from Tabela_de_dados_Inventario_7_2 import (
        LISTA_ALMOXARIFADO_PADRAO,
        UNIDADES_PADRAO,
    )

    assert LISTA_ALMOXARIFADO_PADRAO == ["Almoxarifado Central SESA"]
    assert "Almoxarifado Central SESA" in UNIDADES_PADRAO


def test_auditoria_pre_migracao_usa_colunas_canonicas():
    import auditoria_pre_migracao_postgresql as audit
    import Tabela_de_dados_Inventario_7_2 as backend

    df = backend.pd.DataFrame([{
        "Setor": "Farmacia",
        "Tipo de Patrimônio": "CPU",
        "Nº de Patrimônio": "ALM-001",
        "Fabricante": "Dell",
        "Data Cadastro": "2026-09-23 10:00:00",
        "Foto": "",
    }])

    resultado = audit._auditar_dataframe(
        df, "Almoxarifado Central SESA", "Google Sheets (Almoxarifado Central SESA)"
    )

    assert resultado["linhas"] == 1
    assert resultado["bloqueadores"] == 0
    assert resultado["prontos"] == 1
