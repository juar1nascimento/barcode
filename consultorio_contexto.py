import re
import streamlit as st

_original_selectbox = None


def _normalizar(valor):
    return re.sub(r"\s+", " ", str(valor or "").strip())


def _formatar(numero, especialidade):
    numero = _normalizar(numero)
    especialidade = _normalizar(especialidade)
    if not numero or not especialidade or not numero.isdigit() or int(numero) < 1:
        return ""
    return f"Consultório {int(numero)} - {especialidade}"


def ativar():
    """Ativa temporariamente o contexto número/especialidade do Consultório."""
    global _original_selectbox
    if _original_selectbox is not None:
        return

    _original_selectbox = st.selectbox

    def wrapper(label, options, *args, **kwargs):
        valor = _original_selectbox(label, options, *args, **kwargs)
        if label != "Setor:" or valor != "Consultório":
            return valor

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
        return resultado

    st.selectbox = wrapper


def desativar():
    global _original_selectbox
    if _original_selectbox is not None:
        st.selectbox = _original_selectbox
        _original_selectbox = None
