"""Fachada de compatibilidade da camada legada de inventário.

A persistência real vive em ``persistencia_inventario.py``. Este módulo mantém
os nomes históricos usados por partes antigas do sistema durante a migração.
"""

import re
from typing import Tuple

import pandas as pd
import streamlit as st

from inventario_regras import SETORES_OFICIAIS, TIPOS_PATRIMONIO_OFICIAIS, normalizar_setor
from persistencia_inventario import (
    ARQUIVO_EXCEL,
    COLUNAS_INVENTARIO,
    _valor_texto,
    carregar_dados,
    normalizar_legacy_dataframe,
    normalizar_tipo,
    salvar_dados,
)

COLUNA_CHAVE = "Setor"
COLUNAS_PADRAO = COLUNAS_INVENTARIO.copy()
COLUNAS_OBSOLETAS = ["Data_Hora", "Usuario"]
TIPOS_PATRIMONIO = TIPOS_PATRIMONIO_OFICIAIS
SETORES_PADRAO = list(SETORES_OFICIAIS)
LISTA_URS_PADRAO = ["URS Novo Horizonte", "URS Jacaraípe", "URS Boa Vista", "URS Feu Rosa", "URS Serra Sede", "URS Serra Dourada"]
LISTA_UBS_PADRAO = ["UBS André Carloni", "UBS Bairro de Fátima", "UBS Feu Rosa", "UBS Barcelona", "UBS Barro Branco", "UBS Campinho da Serra", "UBS Carapebus", "UBS Carapina Grande", "UBS Central Carapina", "UBS Cidade Continental", "UBS Eldorado", "UBS Jardim Carapina", "UBS Jardim Tropical", "UBS José de Anchieta", "UBS Laranjeiras Velha", "UBS Manguinhos", "UBS Manoel Plaza", "UBS Nova Almeida", "UBS Nova Carapina I", "UBS Nova Carapina II", "UBS Oceania", "UBS Pitanga", "UBS Planalto Serrano (Bloco A)", "UBS Planalto Serrano (Bloco B)", "UBS Porto Canoa", "UBS São Diogo", "UBS São Marcos", "UBS Taquara I", "UBS Taquara II", "UBS Vila Nova de Colares", "UBS Vista da Serra", "UBS Itinerante (atendimento na UBS)"]
UNIDADES_PADRAO = LISTA_URS_PADRAO + LISTA_UBS_PADRAO


def formatar_nome_patrimonio(patrimonio: str) -> str:
    return _valor_texto(patrimonio)


def formatar_nome_fabricante(patrimonio: str) -> str:
    texto = re.sub(r"\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$", "", _valor_texto(patrimonio), flags=re.I)
    return f"Fabricante {texto}" if texto else "Fabricante"


def _normalizar_tipo(valor: str) -> str:
    return normalizar_tipo(valor)


def _normalizar_unidade_aba(nome: str) -> str:
    aliases = {"URS Jacara_pe": "URS Jacaraípe", "UBS Bairro de F_tima": "UBS Bairro de Fátima"}
    return aliases.get(_valor_texto(nome), _valor_texto(nome))


@st.cache_data(ttl=2)
def carregar_dados_excel(unidade: str) -> Tuple[pd.DataFrame, str]:
    return carregar_dados(_normalizar_unidade_aba(unidade), st.secrets)


def salvar_no_excel(df: pd.DataFrame, unidade: str) -> bool:
    resultado = salvar_dados(df, _normalizar_unidade_aba(unidade), st.secrets)
    carregar_dados_excel.clear()
    return resultado


def registrar_patrimonio(codigo_barras: str, tipo_patrimonio: str, setor: str, unidade: str, fabricante: str = "", numero_patrimonio: str = "") -> bool:
    from persistencia_inventario import registrar_patrimonio as _registrar
    return _registrar(codigo_barras, tipo_patrimonio, setor, _normalizar_unidade_aba(unidade), fabricante, numero_patrimonio, st.secrets)


def adicionar_e_salvar_sem_sobrescrever(codigo: str, patrimonio: str, setor: str, unidade: str, fabricante: str = "", numero_patrimonio: str = "") -> bool:
    return registrar_patrimonio(codigo, patrimonio, setor, unidade, fabricante, numero_patrimonio)


adicionar_e_salvar = adicionar_e_salvar_sem_sobrescrever


def _aplicar_exclusao_setor(df: pd.DataFrame, setor: str) -> Tuple[pd.DataFrame, bool]:
    df = normalizar_legacy_dataframe(df)
    if df.empty:
        return df.copy(), False
    alvo = normalizar_setor(setor).casefold()
    mask = df["Setor"].astype(str).str.strip().str.casefold().eq(alvo)
    return df.loc[~mask].copy(), bool(mask.any())


def excluir_setor(setor: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    novo_df, alterado = _aplicar_exclusao_setor(df, setor)
    return salvar_no_excel(novo_df, unidade) if alterado else False


def _aplicar_exclusao_patrimonio(df: pd.DataFrame, setor: str, coluna: str) -> Tuple[pd.DataFrame, bool]:
    df = normalizar_legacy_dataframe(df)
    if df.empty:
        return df.copy(), False
    alvo = normalizar_setor(setor).casefold()
    subset = df.loc[df["Setor"].astype(str).str.strip().str.casefold().eq(alvo)]
    if subset.empty:
        return df.copy(), False
    indice = subset.index[0]
    return df.drop(index=indice).reset_index(drop=True), True


def excluir_patrimonio(setor: str, coluna: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    novo_df, alterado = _aplicar_exclusao_patrimonio(df, setor, coluna)
    return salvar_no_excel(novo_df, unidade) if alterado else False


__all__ = [
    "ARQUIVO_EXCEL", "COLUNA_CHAVE", "COLUNAS_INVENTARIO", "COLUNAS_PADRAO", "COLUNAS_OBSOLETAS",
    "TIPOS_PATRIMONIO", "SETORES_PADRAO", "LISTA_URS_PADRAO", "LISTA_UBS_PADRAO", "UNIDADES_PADRAO",
    "formatar_nome_patrimonio", "formatar_nome_fabricante", "_normalizar_tipo", "_normalizar_unidade_aba",
    "_valor_texto", "carregar_dados_excel", "salvar_no_excel", "registrar_patrimonio",
    "adicionar_e_salvar_sem_sobrescrever", "adicionar_e_salvar", "_aplicar_exclusao_setor", "excluir_setor",
    "_aplicar_exclusao_patrimonio", "excluir_patrimonio",
]
