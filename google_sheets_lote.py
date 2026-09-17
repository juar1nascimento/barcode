"""Leitura em lote do Google Sheets para auditoria e migração.

A leitura usa spreadsheets.values.batchGet para reduzir dezenas de chamadas
individuais a uma chamada em lote. O resultado é cacheado por 30 segundos,
sem alterar ou gravar qualquer dado na planilha.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd
import streamlit as st

from Tabela_de_dados_Inventario_7_2 import (
    COLUNAS_INVENTARIO,
    _normalizar_legacy_dataframe,
    _nome_aba,
    _normalizar_unidade_aba,
    conectar_google_sheets,
)


def _escapar_nome_aba(nome: str) -> str:
    return str(nome).replace("'", "''")


def _remover_colunas_duplicadas(df: pd.DataFrame) -> pd.DataFrame:
    """Mantém a primeira ocorrência de cada cabeçalho para evitar reindex inválido."""
    if df is None or df.empty:
        return df
    if not df.columns.duplicated().any():
        return df
    return df.loc[:, ~df.columns.duplicated(keep="first")].copy()


@st.cache_data(ttl=30, show_spinner=False)
def _carregar_lote_cache(unidades: tuple[str, ...]) -> dict[str, tuple[pd.DataFrame, str]]:
    """Carrega as abas informadas em uma única chamada values.batchGet."""
    planilha = conectar_google_sheets()
    resultado: dict[str, tuple[pd.DataFrame, str]] = {}
    if not planilha:
        return resultado

    ranges: list[str] = []
    fontes: list[tuple[str, str]] = []
    for unidade in unidades:
        unidade_normalizada = _normalizar_unidade_aba(unidade)
        nome = _nome_aba(unidade_normalizada)
        nomes = [nome]
        if nome == "URS Jacaraípe":
            nomes.append("URS Jacara_pe")
        elif nome == "UBS Bairro de Fátima":
            nomes.append("UBS Bairro de F_tima")
        for nome_aba in nomes:
            ranges.append(f"'{_escapar_nome_aba(nome_aba)}'!A:Z")
            fontes.append((unidade_normalizada, nome_aba))

    try:
        resposta = planilha.values_batch_get(
            ranges,
            params={"majorDimension": "ROWS"},
        )
    except Exception as exc:
        st.warning(f"Leitura em lote do Google Sheets indisponível: {exc}")
        return resultado

    value_ranges = resposta.get("valueRanges", []) if isinstance(resposta, dict) else []
    acumulados: dict[str, list[pd.DataFrame]] = {}
    nomes_fontes: dict[str, list[str]] = {}

    for (unidade, nome_aba), value_range in zip(fontes, value_ranges):
        valores = value_range.get("values", []) if isinstance(value_range, dict) else []
        if not valores:
            continue
        cabecalho = valores[0]
        linhas = valores[1:]
        df_bruto = pd.DataFrame(linhas, columns=cabecalho) if cabecalho else pd.DataFrame()
        df_bruto = _remover_colunas_duplicadas(df_bruto)
        df = _normalizar_legacy_dataframe(df_bruto)
        acumulados.setdefault(unidade, []).append(df)
        nomes_fontes.setdefault(unidade, []).append(nome_aba)

    for unidade in unidades:
        unidade_normalizada = _normalizar_unidade_aba(unidade)
        partes = acumulados.get(unidade_normalizada, [])
        if partes:
            combinado = pd.concat(partes, ignore_index=True)
            combinado = combinado.drop_duplicates(
                subset=["Setor", "Tipo de Patrimônio", "Nº de Patrimônio"],
                keep="first",
            )
            combinado = combinado.reindex(columns=COLUNAS_INVENTARIO, fill_value="")
            origem = f"Google Sheets ({' + '.join(nomes_fontes[unidade_normalizada])})"
            resultado[unidade_normalizada] = (combinado, origem)
        else:
            nome = _nome_aba(unidade_normalizada)
            resultado[unidade_normalizada] = (
                pd.DataFrame(columns=COLUNAS_INVENTARIO),
                f"Google Sheets ({nome})",
            )

    return resultado


def carregar_dados_excel_lote(unidades: Iterable[str]) -> dict[str, tuple[pd.DataFrame, str]]:
    """Retorna os dados das unidades usando uma leitura Google Sheets em lote."""
    normalizadas = tuple(dict.fromkeys(_normalizar_unidade_aba(u) for u in unidades))
    return _carregar_lote_cache(normalizadas)
