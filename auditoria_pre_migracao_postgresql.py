"""Auditoria somente leitura para preparar a migração Google Sheets -> PostgreSQL.

A auditoria NÃO grava, altera ou exclui dados. Ela classifica os registros
carregados do Google Sheets em bloqueadores e alertas antes da migração.
"""
from __future__ import annotations

import re
from datetime import datetime
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
    "computador": "CPU", "cpu": "CPU", "monitor": "Monitores",
    "monitores": "Monitores", "teclado": "Teclado", "mouse": "Mouse",
    "impressora": "Imprenssoras", "impressoras": "Imprenssoras",
    "imprenssoras": "Imprenssoras", "outros dispositivos": "Outros Dispositivos",
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
    for formato in formatos:
        try:
            datetime.strptime(texto, formato)
            return True
        except ValueError:
            pass
    return False


def auditar_unidade(unidade: str) -> dict[str, Any]:
    df, origem = carregar_dados_excel(unidade)
    if df is None:
        df = pd.DataFrame(columns=COLUNAS_INVENTARIO)
    df = df.reindex(columns=COLUNAS_INVENTARIO, fill_value="").fillna("").astype(str)

    bloqueadores: list[dict[str, str]] = []
    alertas: list[dict[str, str]] = []
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
        erros: list[str] = []
        avisos: list[str] = []

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
            avisos.append("fabricante vazio (campo aceito pelo PostgreSQL)")

        base = {"unidade": unidade, "linha": str(linha), "numero": numero}
        if erros:
            bloqueadores.append({**base, "problemas": "; ".join(erros)})
        elif avisos:
            alertas.append({**base, "alertas": "; ".join(avisos)})
            if tipo_legado:
                normalizaveis += 1
            else:
                prontos += 1
        elif tipo_legado:
            normalizaveis += 1
        else:
            prontos += 1

    numeros = df["Nº de Patrimônio"].map(_texto) if not df.empty else pd.Series(dtype=str)
    duplicados_linhas = int(numeros[numeros != ""].duplicated(keep=False).sum())
    duplicados_grupos = int(numeros[numeros != ""].value_counts().gt(1).sum())

    return {
        "unidade": unidade, "origem": origem, "linhas": len(df),
        "prontos": prontos, "normalizaveis": normalizaveis,
        "bloqueadores": len(bloqueadores), "alertas": len(alertas),
        "duplicidades": duplicados_linhas, "grupos_duplicados": duplicados_grupos,
        "problemas": bloqueadores, "avisos": alertas,
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
            "bloqueadores": sum(r["bloqueadores"] for r in resultados),
            "alertas": sum(r["alertas"] for r in resultados),
            "duplicidades": sum(r["duplicidades"] for r in resultados),
            "grupos_duplicados": sum(r["grupos_duplicados"] for r in resultados),
        },
    }


def renderizar_auditoria_pre_migracao() -> None:
    st.title("🔎 Auditoria pré-migração PostgreSQL")
    st.caption("Leitura do Google Sheets. Nenhuma alteração é executada nesta auditoria.")

    if st.button("▶ Executar auditoria agora", type="primary"):
        with st.spinner("Lendo as unidades e classificando os registros..."):
            resultado = auditar_todas_as_unidades()
        st.session_state["resultado_auditoria_pre_pg"] = resultado
        st.session_state.pop("resultado_simulacao_pg", None)

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
    c5.metric("Bloqueadores", totais["bloqueadores"])

    st.subheader("Resumo por unidade")
    resumo = pd.DataFrame([
        {"Unidade": r["unidade"], "Origem": r["origem"], "Linhas": r["linhas"],
         "Prontos": r["prontos"], "Normalizáveis": r["normalizaveis"],
         "Bloqueadores": r["bloqueadores"], "Alertas": r["alertas"],
         "Linhas duplicadas": r["duplicidades"], "Grupos duplicados": r["grupos_duplicados"]}
        for r in resultado["unidades"]
    ])
    st.dataframe(resumo, use_container_width=True, hide_index=True)

    problemas = [p for r in resultado["unidades"] for p in r["problemas"]]
    avisos = [p for r in resultado["unidades"] for p in r["avisos"]]
    if problemas:
        st.subheader("⛔ Bloqueadores")
        st.dataframe(pd.DataFrame(problemas), use_container_width=True, hide_index=True)
    else:
        st.success("Nenhum bloqueador encontrado nas linhas carregadas.")
    if avisos:
        st.subheader("⚠️ Alertas")
        st.dataframe(pd.DataFrame(avisos), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Simulação da migração")
    st.caption("A simulação consulta o PostgreSQL e o Google Sheets, mas não confirma nenhuma gravação no banco.")
    if totais["bloqueadores"] > 0:
        st.warning("A simulação está liberada para análise, mas a migração efetiva deverá aguardar a resolução dos bloqueadores.")

    if st.button("🧪 Executar simulação (sem gravar)"):
        from migrar_google_para_postgresql import migrar_todas_as_unidades
        with st.spinner("Comparando os dados do Google Sheets com o PostgreSQL..."):
            simulacao = migrar_todas_as_unidades(dry_run=True)
        st.session_state["resultado_simulacao_pg"] = simulacao

    simulacao = st.session_state.get("resultado_simulacao_pg")
    if simulacao:
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("Linhas lidas", simulacao["linhas_lidas"])
        s2.metric("Candidatos", simulacao["candidatos"])
        s3.metric("Já existentes", simulacao["ja_existentes"])
        s4.metric("Conflitos", simulacao["conflitos"])
        s5.metric("Erros", simulacao["erros"])
        if simulacao["conflitos"]:
            conflitos = [c for r in simulacao["detalhes"] for c in r["conflitos"]]
            st.error("Foram encontrados conflitos que não serão sobrescritos automaticamente.")
            st.dataframe(pd.DataFrame(conflitos), use_container_width=True, hide_index=True)
        elif simulacao["erros"]:
            st.warning("A simulação encontrou erros que precisam ser analisados antes da migração efetiva.")
        else:
            st.success("Simulação concluída sem conflitos ou erros. Nenhum dado foi gravado.")

    st.warning("A migração efetiva ainda não é executada por esta tela. O Google Sheets permanece intacto.")
