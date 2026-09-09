"""Extensão de interface do setor Consultório.

Mantém a página legada de inventário e acrescenta, sem alterar a estrutura
existente da planilha, os dados específicos do consultório quando a opção
"Consultório" é escolhida no menu Setor.
"""

import re

import streamlit as st

from sistema_inventario import renderizar_sistema_inventario as _renderizar_sistema_inventario


def _normalizar_especialidade(valor: str) -> str:
    return re.sub(r"\s+", " ", str(valor or "").strip())


def montar_setor_consultorio(numero: str, especialidade: str) -> str:
    numero_limpo = str(numero or "").strip()
    especialidade_limpa = _normalizar_especialidade(especialidade)
    if not numero_limpo or not especialidade_limpa:
        return ""
    return f"Consultório {numero_limpo} - {especialidade_limpa}"


def renderizar_sistema_inventario(*args, **kwargs) -> None:
    """Renderiza a tela legada com detalhamento contextual de Consultório."""
    selectbox_original = st.selectbox

    def selectbox_com_consultorio(label, options, *select_args, **select_kwargs):
        resultado = selectbox_original(label, options, *select_args, **select_kwargs)
        if label != "Setor:" or resultado != "Consultório":
            return resultado

        st.markdown("**Detalhamento do Consultório**")
        col_numero, col_especialidade = st.columns([1, 1])
        with col_numero:
            numero = st.text_input(
                "Número do Consultório:",
                placeholder="Ex.: 1, 2, 3...",
                key="numero_consultorio_main_v1",
            )
        with col_especialidade:
            especialidade = st.text_input(
                "Especialidade do Consultório:",
                placeholder="Ex.: Psicologia, Psiquiatria, Fonoaudiologia...",
                key="especialidade_consultorio_main_v1",
            )

        setor_final = montar_setor_consultorio(numero, especialidade)
        if setor_final:
            st.caption(f"Setor a ser registrado: **{setor_final}**")
        else:
            st.info("Informe o número e a especialidade do consultório para continuar.")
        return setor_final

    st.selectbox = selectbox_com_consultorio
    try:
        _renderizar_sistema_inventario(*args, **kwargs)
    finally:
        st.selectbox = selectbox_original
