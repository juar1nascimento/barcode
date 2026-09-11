"""Migração controlada do Google Sheets para PostgreSQL.

Uso recomendado na máquina que consegue acessar o Google Sheets e o PostgreSQL.
A rotina é idempotente: registros já existentes no PostgreSQL são ignorados.
Não apaga nem modifica o Google Sheets.
"""

from typing import Iterable

import pandas as pd

from Tabela_de_dados_Inventario_7_2 import (
    COLUNAS_INVENTARIO,
    LISTA_UBS_PADRAO,
    LISTA_URS_PADRAO,
    carregar_dados_excel,
)
from postgresql_persistencia import conectar, garantir_unidade, garantir_setor


def migrar_unidade(unidade: str) -> tuple[int, int, list[str]]:
    """Migra uma unidade e retorna (lidos, inseridos, erros)."""
    df, origem = carregar_dados_excel(unidade)
    if df is None or df.empty:
        return 0, 0, [f"{unidade}: nenhuma linha encontrada em {origem}."]

    conn = conectar()
    if conn is None:
        return len(df), 0, [f"{unidade}: PostgreSQL indisponível."]

    inseridos = 0
    erros = []
    try:
        with conn.cursor() as cur:
            unidade_id = garantir_unidade(cur, unidade)
            for _, row in df.reindex(columns=COLUNAS_INVENTARIO, fill_value="").iterrows():
                numero = str(row.get("Nº de Patrimônio", "") or "").strip()
                tipo = str(row.get("Tipo de Patrimônio", "") or "").strip()
                setor = str(row.get("Setor", "") or "").strip()
                fabricante = str(row.get("Fabricante", "") or "").strip() or None
                data_cadastro = str(row.get("Data Cadastro", "") or "").strip()

                if not numero or not tipo or not setor:
                    erros.append(f"{unidade}: linha ignorada por dados obrigatórios ausentes.")
                    continue

                setor_id = garantir_setor(cur, unidade_id, setor)
                cur.execute(
                    "SELECT id FROM patrimonios WHERE numero_patrimonio = %s",
                    (numero,),
                )
                if cur.fetchone():
                    continue

                cur.execute(
                    """INSERT INTO patrimonios
                         (unidade_id, setor_id, tipo, numero_patrimonio, fabricante,
                          data_cadastro, atualizado_em)
                       VALUES (%s, %s, %s, %s, %s,
                               COALESCE(NULLIF(%s, '')::timestamptz, NOW()), NOW())""",
                    (unidade_id, setor_id, tipo, numero, fabricante, data_cadastro),
                )
                inseridos += 1
        conn.commit()
    except Exception as exc:
        conn.rollback()
        erros.append(f"{unidade}: falha na transação: {exc}")
    finally:
        conn.close()

    return len(df), inseridos, erros


def migrar_todas_as_unidades(unidades: Iterable[str] | None = None) -> dict:
    unidades = list(unidades or (LISTA_URS_PADRAO + LISTA_UBS_PADRAO))
    resumo = {"unidades": 0, "linhas_lidas": 0, "linhas_inseridas": 0, "erros": []}
    for unidade in unidades:
        resumo["unidades"] += 1
        lidos, inseridos, erros = migrar_unidade(unidade)
        resumo["linhas_lidas"] += lidos
        resumo["linhas_inseridas"] += inseridos
        resumo["erros"].extend(erros)
    return resumo


if __name__ == "__main__":
    print("A migração deve ser executada dentro de um ambiente Streamlit/configurado com st.secrets.")
