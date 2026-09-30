"""Regressão do fluxo patrimônio -> ID PostgreSQL -> foto.

O teste garante que uma falha no Google Sheets não interrompa o vínculo
necessário para armazenar a fotografia no Supabase.
"""

import pandas as pd


def test_id_do_patrimonio_e_preservado_quando_sheets_falha(monkeypatch):
    import Tabela_de_dados_Inventario_7_2 as tabela

    monkeypatch.setattr(tabela.st, "session_state", {})
    monkeypatch.setattr(
        tabela,
        "carregar_dados_excel",
        lambda unidade: (
            pd.DataFrame(columns=tabela.COLUNAS_INVENTARIO),
            "postgresql",
        ),
    )
    monkeypatch.setattr(tabela, "conectar_google_sheets", lambda: None)
    monkeypatch.setattr(
        tabela,
        "_numero_patrimonio_existe_na_planilha",
        lambda planilha, numero: False,
    )
    monkeypatch.setattr(
        tabela,
        "validar_cadastro_patrimonio",
        lambda tipo, setor, unidade, numero: (True, ""),
    )
    monkeypatch.setattr(
        tabela,
        "salvar_patrimonio",
        lambda **kwargs: (True, 42, "Patrimônio gravado no PostgreSQL."),
    )
    monkeypatch.setattr(tabela, "_anexar_no_google", lambda *args, **kwargs: False)

    ok = tabela.registrar_patrimonio(
        codigo_barras="2Q0P7XA009796",
        tipo_patrimonio="CPU",
        setor="Almoxarifado",
        unidade="Almoxarifado Central SESA",
        fabricante="Dell",
    )

    assert ok is True
    assert tabela.st.session_state["ultimo_patrimonio_id"] == 42
    assert tabela.st.session_state["ultimo_patrimonio_numero"] == "2Q0P7XA009796"
    assert (
        tabela.st.session_state["ultimo_patrimonio_unidade"]
        == "Almoxarifado Central SESA"
    )
