"""Auditoria somente leitura de reconciliação Google Sheets x PostgreSQL.

Não grava nem altera Google Sheets ou PostgreSQL.
A finalidade é diagnosticar divergências antes da migração definitiva.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from google_sheets_lote import carregar_dados_excel_lote
import postgresql_persistencia


def _norm(value) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def _chave_numero(row, coluna="Nº de Patrimônio") -> str:
    return _norm(row.get(coluna, ""))


def _carregar_postgresql(unidade: str) -> pd.DataFrame:
    registros = postgresql_persistencia.listar_patrimonios(unidade=unidade)
    colunas = [
        "id", "unidade", "setor", "numero_consultorio", "especialidade",
        "tipo", "numero_patrimonio", "codigo_barras", "fabricante",
        "data_cadastro", "atualizado_em", "possui_foto",
    ]
    return pd.DataFrame(registros, columns=colunas)


def auditar_unidade(unidade: str, dados_sheets=None) -> dict:
    """Compara uma unidade sem executar qualquer escrita."""
    if dados_sheets is None:
        dados_sheets = carregar_dados_excel_lote([unidade])

    df_sheets, origem = dados_sheets.get(
        unidade, (pd.DataFrame(), f"Google Sheets ({unidade})")
    )
    df_sheets = df_sheets.copy() if df_sheets is not None else pd.DataFrame()
    df_pg = _carregar_postgresql(unidade)

    sheets_chaves = {}
    for _, row in df_sheets.iterrows():
        sheets_chaves[_chave(row)] = {
            "setor": str(row.get("Setor", "")),
            "tipo": str(row.get("Tipo de Patrimônio", "")),
            "numero": str(row.get("Nº de Patrimônio", "")),
            "fabricante": str(row.get("Fabricante", "")),
        }

    pg_chaves = {}
    for _, row in df_pg.iterrows():
        chave = (_norm(row["setor"]), _norm(row["tipo"]), _norm(row["numero_patrimonio"]))
        pg_chaves[chave] = {
            "setor": str(row["setor"] or ""),
            "tipo": str(row["tipo"] or ""),
            "numero": str(row["numero_patrimonio"] or ""),
            "fabricante": str(row["fabricante"] or ""),
            "possui_foto": bool(row["possui_foto"]),
        }

    somente_sheets = sorted(set(sheets_chaves) - set(pg_chaves))
    somente_pg = sorted(set(pg_chaves) - set(sheets_chaves))
    comuns = sorted(set(sheets_chaves) & set(pg_chaves))

    divergentes = []
    for chave in comuns:
        s = sheets_chaves[chave]
        p = pg_chaves[chave]
        if _norm(s["fabricante"]) != _norm(p["fabricante"]):
            divergentes.append({
                "numero": p["numero"],
                "campo": "Fabricante",
                "sheets": s["fabricante"],
                "postgresql": p["fabricante"],
            })

    duplicados_sheets = int(
        df_sheets["Nº de Patrimônio"].map(_norm).duplicated(keep=False).sum()
    ) if "Nº de Patrimônio" in df_sheets.columns else 0

    duplicados_pg = int(
        df_pg["numero_patrimonio"].map(_norm).duplicated(keep=False).sum()
    ) if not df_pg.empty else 0

    return {
        "unidade": unidade,
        "origem_sheets": origem,
        "sheets_total": len(df_sheets),
        "postgresql_total": len(df_pg),
        "iguais": len(comuns) - len(divergentes),
        "somente_sheets": len(somente_sheets),
        "somente_postgresql": len(somente_pg),
        "divergencias": len(divergentes),
        "duplicados_sheets": duplicados_sheets,
        "duplicados_postgresql": duplicados_pg,
        "fotos_postgresql": int(df_pg["possui_foto"].sum()) if not df_pg.empty else 0,
        "detalhes_somente_sheets": somente_sheets,
        "detalhes_somente_postgresql": somente_pg,
        "detalhes_divergencias": divergentes,
    }


def auditar_todas_as_unidades(unidades: Iterable[str]) -> dict:
    unidades = list(dict.fromkeys(str(u).strip() for u in unidades if str(u).strip()))
    dados = carregar_dados_excel_lote(unidades)
    resultados = [auditar_unidade(u, dados_sheets=dados) for u in unidades]
    return {
        "unidades": len(resultados),
        "sheets_total": sum(r["sheets_total"] for r in resultados),
        "postgresql_total": sum(r["postgresql_total"] for r in resultados),
        "iguais": sum(r["iguais"] for r in resultados),
        "somente_sheets": sum(r["somente_sheets"] for r in resultados),
        "somente_postgresql": sum(r["somente_postgresql"] for r in resultados),
        "divergencias": sum(r["divergencias"] for r in resultados),
        "duplicados_sheets": sum(r["duplicados_sheets"] for r in resultados),
        "duplicados_postgresql": sum(r["duplicados_postgresql"] for r in resultados),
        "fotos_postgresql": sum(r["fotos_postgresql"] for r in resultados),
        "detalhes": resultados,
    }


if __name__ == "__main__":
    from Tabela_de_dados_Inventario_7_2 import UNIDADES_PADRAO

    resultado = auditar_todas_as_unidades(UNIDADES_PADRAO)
    print(resultado)
