"""Ponte de persistência dupla para o módulo de inventário.

Quando a Secret [postgresql] estiver configurada, cada novo cadastro passa
primeiro pelo PostgreSQL e depois pelo Google Sheets. Sem PostgreSQL configurado,
o comportamento existente do Google Sheets permanece inalterado.
"""

import streamlit as st

import postgresql_persistencia

_original = None


def ativar():
    """Ativa o espelhamento PostgreSQL + Google Sheets durante a página."""
    global _original
    if _original is not None:
        return

    import sistema_inventario
    _original = sistema_inventario.adicionar_e_salvar

    def wrapper(codigo, patrimonio, setor, unidade, fabricante=""):
        if not postgresql_persistencia._conexao_configurada():
            return _original(codigo, patrimonio, setor, unidade, fabricante)

        ok_pg, msg_pg = postgresql_persistencia.salvar_patrimonio(
            codigo_barras=codigo,
            tipo=patrimonio,
            setor=setor,
            unidade=unidade,
            fabricante=fabricante,
        )
        if not ok_pg:
            st.error(f"❌ Cadastro não concluído: {msg_pg}")
            return False

        ok_sheets = _original(codigo, patrimonio, setor, unidade, fabricante)
        if not ok_sheets:
            st.warning(
                "⚠️ O patrimônio foi gravado no PostgreSQL, mas o Google Sheets "
                "não confirmou o espelhamento. O registro não foi descartado. "
                "Será necessário sincronizar o Sheets posteriormente."
            )
            return False
        return True

    sistema_inventario.adicionar_e_salvar = wrapper


def desativar():
    global _original
    if _original is None:
        return
    import sistema_inventario
    sistema_inventario.adicionar_e_salvar = _original
    _original = None
