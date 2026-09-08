import streamlit as st

from Tabela_de_dados_Inventario_7_2 import UNIDADES_PADRAO
from movimentacao_inventario import registrar_saida


def renderizar_card_saida(lista_urs, lista_ubs):
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📤 Saída de Equipamentos</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Acesse a ferramenta de baixa, transferência e saída de equipamentos.</p>", unsafe_allow_html=True)
        st.write("")

        urs_saida = st.selectbox("URS - Unidade Regional de Saúde", lista_urs, key="sel_urs_saida")
        ubs_saida = st.selectbox("UBS - Unidade Básica de Saúde", lista_ubs, key="sel_ubs_saida")
        if urs_saida != "Selecione uma URS...":
            st.session_state.saved_setor = urs_saida
        elif ubs_saida != "Selecione uma UBS...":
            st.session_state.saved_setor = ubs_saida

        st.write("")
        if st.button("📂 Abrir Saída nesta Aba", use_container_width=True, type="primary", key="btn_saida"):
            st.session_state.pagina_atual = "saida"
            st.rerun()


def renderizar_sistema_saida():
    st.title("📤 Saída de Equipamentos - GTI-SESA")
    st.markdown("Módulo para controle de movimentação, recolhimento, manutenção ou descarte de equipamentos.")
    st.divider()

    unidade_atual = st.session_state.get("saved_setor", "")
    st.info(f"📍 Unidade de Origem Selecionada: **{unidade_atual or 'Nenhuma unidade selecionada'}**")

    st.subheader("1. Motivo da Saída")
    motivo = st.selectbox("Motivo da movimentação:", [
        "Transferência para outra Unidade",
        "Envio para Manutenção / Conserto",
        "Recolhimento / Desfazimento (Baixa)",
        "Outro",
    ], key="saida_motivo")

    destino = ""
    if motivo == "Transferência para outra Unidade":
        opcoes_destino = [u for u in UNIDADES_PADRAO if u.casefold() != unidade_atual.casefold()]
        destino = st.selectbox("Unidade de Destino:", opcoes_destino, key="saida_destino")

    observacoes = st.text_area("Observações / Justificativa:", placeholder="Descreva os detalhes da saída...", key="saida_observacoes")

    st.subheader("2. Identificação do Equipamento")
    codigo_saida = st.text_input("Bipe ou digite o código de patrimônio para saída:", placeholder="Aguardando bipagem...", key="saida_codigo")

    if st.button("🚨 Registrar Saída de Equipamento", type="primary", use_container_width=True, key="btn_registrar_saida"):
        if not unidade_atual:
            st.warning("Selecione uma unidade no Portal antes de registrar a saída.")
        elif not codigo_saida.strip():
            st.warning("Informe ou bipe o código do equipamento antes de confirmar.")
        else:
            sucesso, mensagem = registrar_saida(codigo_saida.strip(), unidade_atual, motivo, destino.strip(), observacoes.strip())
            if sucesso:
                st.success(mensagem)
                st.info("A alteração foi persistida no inventário da unidade.")
            else:
                st.error(mensagem)
