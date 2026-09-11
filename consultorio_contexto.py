import re
import streamlit as st


def _normalizar_texto(valor: str) -> str:
    return re.sub(r"\s+", " ", str(valor or "").strip())


def _formatar_setor_consultorio(numero: str, especialidade: str) -> str:
    numero = _normalizar_texto(numero)
    especialidade = _normalizar_texto(especialidade)
    if not numero or not especialidade:
        return ""
    if not numero.isdigit() or int(numero) < 1:
        return ""
    return f"Consultório {int(numero)} - {especialidade}"


def renderizar_com_contexto_consultorio(render_func):
    """Adiciona identificação do consultório sem alterar o núcleo do inventário.

    O sistema legado já utiliza o setor no formato "Consultório N - Especialidade".
    Esta camada restaura essa regra apenas quando o setor selecionado é Consultório.
    """
    original_selectbox = st.selectbox

    def selectbox_com_contexto(label, options, *args, **kwargs):
        valor = original_selectbox(label, options, *args, **kwargs)
        if label != "Setor:" or valor != "Consultório":
            return valor

        st.markdown("##### 🩺 Identificação do Consultório")
        col_num, col_esp = st.columns(2)
        with col_num:
            numero = st.text_input(
                "Número do Consultório:",
                placeholder="Ex.: 5",
                key="consultorio_numero",
            )
        with col_esp:
            especialidade = st.text_input(
                "Especialidade do Consultório:",
                placeholder="Ex.: Enfermaria, Odontologia, Clínico...",
                key="consultorio_especialidade",
            )

        setor_formatado = _formatar_setor_consultorio(numero, especialidade)
        numero_limpo = _normalizar_texto(numero)
        if numero_limpo and (not numero_limpo.isdigit() or int(numero_limpo) < 1):
            st.warning("Informe somente um número de consultório maior que zero (ex.: 5).")

        if not setor_formatado:
            st.info("Informe o número e a especialidade para identificar o consultório.")
            return ""
        return setor_formatado
