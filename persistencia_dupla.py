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
        """Delega para a rotina canônica de persistência.

        registrar_patrimonio() já grava PostgreSQL de forma atômica e depois
        confirma o espelhamento no Google Sheets. A versão anterior gravava
        PostgreSQL duas vezes: a segunda tentativa encontrava a chave única
        já criada e impedia a gravação no Sheets.
        """
        return _original(codigo, patrimonio, setor, unidade, fabricante)

    sistema_inventario.adicionar_e_salvar = wrapper


def desativar():
    global _original
    if _original is None:
        return
    import sistema_inventario
    sistema_inventario.adicionar_e_salvar = _original
    _original = None
