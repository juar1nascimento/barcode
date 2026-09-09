"""Saneamento seguro de dados legados do inventário.

A rotina trabalha sempre sobre o schema canônico de cinco colunas. Por padrão,
ela apenas calcula o plano de saneamento (dry-run); a escrita só ocorre quando
``aplicar=True`` é informado explicitamente pelo código chamador.
"""

from dataclasses import dataclass
from typing import List

import pandas as pd

import Tabela_de_dados_Inventario_7_2 as backend


@dataclass(frozen=True)
class RelatorioSaneamento:
    unidade: str
    linhas_lidas: int
    linhas_validas: int
    linhas_removidas: int
    duplicatas_removidas: int
    linhas_resultado: int
    alterado: bool
    motivos: tuple


def preparar_saneamento(df: pd.DataFrame, unidade: str) -> tuple[pd.DataFrame, RelatorioSaneamento]:
    """Monta o resultado canônico sem gravar nada.

    Regras conservadoras:
    - remove linhas sem Setor, Tipo de Patrimônio ou Nº de Patrimônio;
    - converte aliases conhecidos de tipo para o catálogo oficial;
    - mantém apenas as cinco colunas canônicas;
    - remove duplicatas pelo número de patrimônio, preservando a primeira;
    - não inventa fabricante, setor, tipo ou número para linhas incompletas.
    """
    bruto = pd.DataFrame(df).copy() if df is not None else pd.DataFrame()
    linhas_lidas = len(bruto)
    normalizado = backend._normalizar_legacy_dataframe(bruto).copy()
    if "Tipo de Patrimônio" in normalizado.columns:
        normalizado["Tipo de Patrimônio"] = normalizado["Tipo de Patrimônio"].map(backend._normalizar_tipo)
    linhas_validas = len(normalizado)
    removidas_incompletas = max(0, linhas_lidas - linhas_validas)

    antes_dedup = len(normalizado)
    resultado = normalizado.drop_duplicates(
        subset=["Setor", "Tipo de Patrimônio", "Nº de Patrimônio"],
        keep="first",
    ).reset_index(drop=True)
    duplicatas = antes_dedup - len(resultado)

    motivos: List[str] = []
    if removidas_incompletas:
        motivos.append(f"{removidas_incompletas} linha(s) incompleta(s) removida(s)")
    if duplicatas:
        motivos.append(f"{duplicatas} duplicata(s) removida(s)")

    relatorio = RelatorioSaneamento(
        unidade=backend._normalizar_unidade_aba(unidade),
        linhas_lidas=linhas_lidas,
        linhas_validas=linhas_validas,
        linhas_removidas=linhas_lidas - len(resultado),
        duplicatas_removidas=duplicatas,
        linhas_resultado=len(resultado),
        alterado=linhas_lidas != len(resultado),
        motivos=tuple(motivos),
    )
    return resultado.reindex(columns=backend.COLUNAS_INVENTARIO, fill_value=""), relatorio


def sanear_unidade(unidade: str, aplicar: bool = False) -> RelatorioSaneamento:
    """Analisa uma unidade e, somente com ``aplicar=True``, grava o resultado.

    O modo padrão é deliberadamente somente leitura para evitar alteração
    acidental dos dados de produção.
    """
    unidade_limpa = backend._normalizar_unidade_aba(unidade)
    df, _ = backend.carregar_dados_excel(unidade_limpa)
    resultado, relatorio = preparar_saneamento(df, unidade_limpa)

    if aplicar and relatorio.alterado:
        if not backend.salvar_no_excel(resultado, unidade_limpa):
            raise RuntimeError(
                f"Falha ao confirmar o saneamento da unidade {unidade_limpa!r} no Google Sheets."
            )
    return relatorio
