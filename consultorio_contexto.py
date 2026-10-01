import re
import streamlit as st


def _normalizar(valor):
    return re.sub(r"\s+", " ", str(valor or "").strip())


def _formatar(numero, especialidade):
    numero = _normalizar(numero)
    especialidade = _normalizar(especialidade)
    if not numero or not especialidade or not numero.isdigit() or int(numero) < 1:
        return ""
    return f"Consultório {int(numero)} - {especialidade}"


def selecionar_setor(opcoes):
    """Renderiza o setor sem alterar globalmente nenhuma API do Streamlit.

    O código anterior substituía st.selectbox em tempo de execução. Isso podia
    sobreviver a reruns/hot-reload e atingir a tela de login. O contexto agora
    é totalmente local à tela do inventário.
    """
    setor_selecionado = st.selectbox(
        "Setor:",
        opcoes,
        index=None,
        placeholder="Selecione um setor...",
    )
    if setor_selecionado != "Consultório":
        return setor_selecionado or ""

    st.markdown("##### 🩺 Identificação do Consultório")
    c1, c2 = st.columns(2)
    with c1:
        numero = st.text_input(
            "Número do Consultório:",
            placeholder="Ex.: 5",
            key="consultorio_numero",
        )
    with c2:
        especialidade = st.text_input(
            "Especialidade do Consultório:",
            placeholder="Ex.: Odontologia, Clínico, Enfermagem...",
            key="consultorio_especialidade",
        )

    numero_limpo = _normalizar(numero)
    if numero_limpo and (not numero_limpo.isdigit() or int(numero_limpo) < 1):
        st.warning("Informe somente um número de consultório maior que zero (ex.: 5).")

    resultado = _formatar(numero, especialidade)
    if not resultado:
        st.info("Informe o número e a especialidade para identificar o consultório.")
    return resultado or "Consultório"
