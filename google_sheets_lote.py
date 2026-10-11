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
    aliases_por_unidade: dict[str, str] = {
        "URS Jacaraípe": "URS Jacara_pe",
        "UBS Bairro de Fátima": "UBS Bairro de F_tima",
    }
    for unidade in unidades:
        unidade_normalizada = _normalizar_unidade_aba(unidade)
        nome = _nome_aba(unidade_normalizada)
        ranges.append(f"'{_escapar_nome_aba(nome)}'!A:Z")
        fontes.append((unidade_normalizada, nome))

    # Primeiro tenta uma única leitura em lote apenas com os nomes canônicos.
    # Uma única aba inexistente não deve zerar os dados das outras unidades.
    value_ranges: list[dict] = []
    try:
        resposta = planilha.values_batch_get(
            ranges,
            params={"majorDimension": "ROWS"},
        )
        value_ranges = resposta.get("valueRanges", []) if isinstance(resposta, dict) else []
        if len(value_ranges) != len(fontes):
            raise ValueError(
                f"Resposta incompleta do batchGet: {len(value_ranges)} de {len(fontes)} intervalos."
            )
    except Exception as exc:
        st.warning(
            "Leitura em lote indisponível; tentando cada aba separadamente "
            f"para preservar as unidades legíveis. Detalhe: {exc}"
        )
        value_ranges = []
        fontes_recuperadas: list[tuple[str, str]] = []
        for unidade, nome in fontes:
            intervalo = f"'{_escapar_nome_aba(nome)}'!A:Z"
            try:
                individual = planilha.values_get(
                    intervalo,
                    params={"majorDimension": "ROWS"},
                )
                value_ranges.append(individual if isinstance(individual, dict) else {})
                fontes_recuperadas.append((unidade, nome))
                continue
            except Exception as erro_canonico:
                alias = aliases_por_unidade.get(unidade)
                if alias:
                    intervalo_alias = f"'{_escapar_nome_aba(alias)}'!A:Z"
                    try:
                        individual = planilha.values_get(
                            intervalo_alias,
                            params={"majorDimension": "ROWS"},
                        )
                        value_ranges.append(individual if isinstance(individual, dict) else {})
                        fontes_recuperadas.append((unidade, alias))
                        continue
                    except Exception as erro_alias:
                        st.error(
                            f"Falha de leitura da unidade '{unidade}': "
                            f"nome principal '{nome}' e alternativa '{alias}' falharam. "
                            f"Detalhes: {erro_canonico}; {erro_alias}"
                        )
                else:
                    st.error(
                        f"Falha de leitura da unidade '{unidade}' na aba '{nome}': "
                        f"{erro_canonico}"
                    )
                # Mantém a posição para que a associação unidade/resultado não desalinhe.
                value_ranges.append({"values": []})
                fontes_recuperadas.append((unidade, f"FALHA DE LEITURA: {nome}"))
        fontes = fontes_recuperadas

    # Se o lote canônico funcionou, só tenta alias quando a aba canônica veio vazia.
    # Isso evita solicitar aliases inexistentes em toda execução normal.
    if len(value_ranges) == len(fontes):
        for idx, (unidade, nome) in enumerate(list(fontes)):
            valores = value_ranges[idx].get("values", []) if isinstance(value_ranges[idx], dict) else []
            alias = aliases_por_unidade.get(unidade)
            if valores or not alias or nome.startswith("FALHA DE LEITURA"):
                continue
            try:
                individual = planilha.values_get(
                    f"'{_escapar_nome_aba(alias)}'!A:Z",
                    params={"majorDimension": "ROWS"},
                )
                if isinstance(individual, dict) and individual.get("values"):
                    value_ranges[idx] = individual
                    fontes[idx] = (unidade, alias)
            except Exception:
                # Alias é opcional: aba canônica vazia continua sendo um resultado válido.
                pass

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
            falha = next(
                (
                    fonte for unidade_fonte, fonte in fontes
                    if unidade_fonte == unidade_normalizada and fonte.startswith("FALHA DE LEITURA")
                ),
                None,
            )
            origem = f"Google Sheets ({falha})" if falha else f"Google Sheets ({nome})"
            resultado[unidade_normalizada] = (
                pd.DataFrame(columns=COLUNAS_INVENTARIO),
                origem,
            )

    return resultado


def carregar_dados_excel_lote(unidades: Iterable[str]) -> dict[str, tuple[pd.DataFrame, str]]:
    """Retorna os dados das unidades usando uma leitura Google Sheets em lote."""
    normalizadas = tuple(dict.fromkeys(_normalizar_unidade_aba(u) for u in unidades))
    return _carregar_lote_cache(normalizadas)
