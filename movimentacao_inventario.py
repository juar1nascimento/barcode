"""Compatibilidade: a lógica de movimentação vive em servicos.movimentacao."""

from servicos.movimentacao import (
    COLUNAS_INVENTARIO,
    _carregar,
    carregar_dados_excel,
    salvar_no_excel,
    registrar_entrada,
    registrar_saida,
    excluir_patrimonio_exato,
)

__all__ = [
    "COLUNAS_INVENTARIO",
    "_carregar",
    "carregar_dados_excel",
    "salvar_no_excel",
    "registrar_entrada",
    "registrar_saida",
    "excluir_patrimonio_exato",
]
