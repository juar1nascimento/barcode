"""Auditoria somente leitura para preparar a migração Google Sheets -> PostgreSQL.

Esta rotina NÃO grava, altera ou exclui dados. Ela usa o carregamento já existente
 do projeto e classifica os registros antes da migração histórica.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from Tabela_de_dados_Inventario_7_2 import (
    COLUNAS_INVENTARIO,
    TIPOS_PATRIMONIO,
    UNIDADES_PADRAO,
    carregar_dados_excel,
)

TIPOS_LEGADOS = {
    "computador": "CPU",
    "cpu": "CPU",
    "monitor": "Monitores",
    "monitores": "Monitores",
    "teclado": "Teclado",
    "mouse": "Mouse",
    "impressora": "Imprenssoras",
    "impressoras": "Imprenssoras",
    "imprenssoras": "Imprenssoras",
    "outros dispositivos": "Outros Dispositivos",
}


def _texto(valor: Any) -> str:
    return re.sub(r"\s+", " ", str(valor or "").strip())


def _tipo_normalizado(valor: Any) -> tuple[str, bool]:
    original = _texto(valor)
    normalizado = TIPOS_LEGADOS.get(original.casefold(), original)
    return normalizado, bool(original) and normalizado != original


def _consultorio(setor: str) -> tuple[bool, bool, bool]:
    texto = _texto(setor)
    if texto.casefold() != "consultório" and not texto.casefold().startswith("consultório "):
        return False, True, True
    completo = re.fullmatch(r"Consultório\s+(\d+)\s*-\s*(.+)", texto, flags=re.I)
    if not completo:
        return True, False, False
    return True, True, bool(_texto(completo.group(2)))


def auditar_unidade(unidade: str) -> dict[str, Any]:
    df, origem = carregar_dados_excel(unidade)
    if df is None:
        df = pd.DataFrame(columns=COLUNAS_INVENTARIO)
    df = df.reindex(columns=COLUNAS_INVENTARIO, fill_value="").fillna("").astype(str)

    problemas: list[dict[str, str]] = []
    prontos = 0
    normalizaveis = 0
    for idx, row in df.iterrows():
        linha = idx + 2
        setor = _texto(row["Setor"])
        tipo_original = _texto(row["Tipo de Patrimônio"])
        numero = _texto(row["Nº de Patrimônio"])
        tipo, tipo_legado = _tipo_normalizado(tipo_original)
        _, consultorio_ok_numero, consultorio_ok_especialidade = _consultorio(setor)
        erros = []
        if not numero:
            erros.append("número de patrimônio vazio")
        if not setor:
            erros.append("setor vazio")
        if not tipo_original:
            erros.append("tipo de patrimônio vazio")
        elif tipo not in TIPOS_PATRIMONIO:
            erros.append(f"tipo inválido: {tipo_original}")
        if setor.casefold() == "consultório" or setor.casefold().startswith("consultório "):
            if not consultorio_ok_numero:
                erros.append("consultório sem número/especialidade no formato esperado")
            elif not consultorio_ok_especialidade:
                erros.append("consultório sem especialidade")
        if erros:
            problemas.append({"unidade": unidade, "linha": str(linha), "numero": numero, "problemas": "; ".join(erros)})
        elif tipo_legado:
            normalizaveis += 1
        else:
            prontos += 1

    duplicados = 0
    if not df.empty:
        numeros = df["Nº de Patrimônio"].map(_texto)
        duplicados = int(numeros[numeros != ""].duplicated(keep=False).sum())

    return {
        "unidade": unidade,
        "origem": origem,
        "linhas": len(df),
        "prontos": prontos,
        "normalizaveis": normalizaveis,
        "com_problemas": len(problemas),
        "duplicidades": duplicados,
        "problemas": problemas,
    }


def auditar_todas_as_unidades(unidades=None) -> dict[str, Any]:
    unidades = list(unidades or UNIDADES_PADRAO)
    resultados = [auditar_unidade(u) for u in unidades]
    return {
        "unidades": resultados,
        "totais": {
            "unidades": len(resultados),
            "linhas": sum(r["linhas"] for r in resultados),
            "prontos": sum(r["prontos"] for r in resultados),
            "normalizaveis": sum(r["normalizaveis"] for r in resultados),
            "com_problemas": sum(r["com_problemas"] for r in resultados),
            "duplicidades": sum(r["duplicidades"] for r in resultados),
        },
    }
