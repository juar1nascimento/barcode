"""Auditoria somente leitura para preparar a migração Google Sheets -> PostgreSQL.

Esta rotina NÃO grava, altera ou exclui dados. Ela usa o carregamento já existente
 do projeto e classifica os registros antes da migração histórica.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd
import streamlit as st

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


def _data_valida(valor: Any) -> bool:
    texto = _texto(valor)
    if not texto:
        return True
    formatos = ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S")
    return any(_tenta_data(texto, formato) for formato in formatos)


def _tenta_data(texto: str, formato: str) -> bool:
    from datetime import datetime
    try:
        datetime.strptime(texto, formato)
        return True
    except ValueError:
        return False


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
        fabricante = _texto(row["Fabricante"])
        data_cadastro = _texto(row["Data Cadastro"])
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
        if data_cadastro and not _data_valida(data_cadastro):
            erros.append("Data Cadastro em formato não reconhecido")
        if not fabricante:
            erros.append("fabricante vazio")
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


def renderizar_auditoria_pre_migracao() -> None:
    """Exibe a auditoria em modo somente leitura."""
    st.title("🔎 Auditoria pré-migração PostgreSQL")
    st.caption("Leitura do Google Sheets para classificação dos dados. Nenhuma alteração é executada.")

    if st.button("▶ Executar auditoria agora", type="primary"):
        with st.spinner("Lendo as unidades e classificando os registros..."):
            resultado = auditar_todas_as_unidades()
        st.session_state["resultado_auditoria_pre_pg"] = resultado

    resultado = st.session_state.get("resultado_auditoria_pre_pg")
    if not resultado:
        st.info("Clique em 'Executar auditoria agora' para gerar o relatório.")
        return

    totais = resultado["totais"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Unidades", totais["unidades"])
    c2.metric("Linhas", totais["linhas"])
    c3.metric("Prontos", totais["prontos"])
    c4.metric("Normalizáveis", totais["normalizaveis"])
    c5.metric("Com problemas", totais["com_problemas"])

    st.subheader("Resumo por unidade")
    resumo = pd.DataFrame([
        {
            "Unidade": r["unidade"],
            "Origem": r["origem"],
            "Linhas": r["linhas"],
            "Prontos": r["prontos"],
            "Normalizáveis": r["normalizaveis"],
            "Com problemas": r["com_problemas"],
            "Duplicidades": r["duplicidades"],
        }
        for r in resultado["unidades"]
    ])
    st.dataframe(resumo, use_container_width=True, hide_index=True)

    problemas = [p for r in resultado["unidades"] for p in r["problemas"]]
    if problemas:
        st.subheader("Registros que exigem atenção")
        st.dataframe(pd.DataFrame(problemas), use_container_width=True, hide_index=True)
    else:
        st.success("Nenhum problema foi encontrado nas linhas carregadas.")

    st.divider()
    st.warning("Esta tela não executa migração, não grava no PostgreSQL e não altera o Google Sheets.")
