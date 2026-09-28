import streamlit as st

from postgresql_persistencia import listar_setores_unidade, registrar_movimentacao_patrimonio, transferir_patrimonio

def renderizar_card_saida(lista_urs, lista_ubs, navegar_saida=None):
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📤 Saída de Equipamentos</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Acesse a ferramenta de baixa, transferência e saída de equipamentos.</p>", unsafe_allow_html=True)
        with st.container(horizontal=True, wrap=True, gap="small"):
            urs_saida = st.selectbox("URS - Unidade Regional de Saúde", lista_urs, key="sel_urs_saida")
            ubs_saida = st.selectbox("UBS - Unidade Básica de Saúde", lista_ubs, key="sel_ubs_saida")
        if st.button("📂 Abrir Saída nesta Aba", use_container_width=True, type="primary", key="btn_saida"):
            selecionada = urs_saida if urs_saida != "Selecione uma URS..." else (ubs_saida if ubs_saida != "Selecione uma UBS..." else "")
            if not selecionada:
                st.warning("⚠️ Selecione a unidade antes de continuar.")
                return
            st.session_state["saved_setor_saida"] = selecionada
            if navegar_saida is not None:
                navegar_saida()
            else:
                st.rerun()


def renderizar_sistema_saida(lista_urs=None, lista_ubs=None):
    st.title("📤 Saída de Equipamentos - GTI-SESA")
    st.markdown("Módulo para controle de movimentação, recolhimento, manutenção ou descarte de equipamentos.")
    st.divider()

    setor_atual = st.session_state.get("saved_setor_saida", "Unidade não selecionada")
    st.info(f"📍 Unidade de Origem Selecionada: **{setor_atual}**")

    st.subheader("1. Motivo da Saída")
    motivo = st.selectbox("Motivo da movimentação:", [
        "Transferência para outra Unidade", 
        "Envio para Manutenção / Conserto", 
        "Recolhimento / Desfazimento (Baixa)", 
        "Outro"
    ])
    
    unidade_destino = ""
    setor_destino = ""
    if motivo == "Transferência para outra Unidade":
        opcoes_destino = [
            u for u in (list(lista_urs or []) + list(lista_ubs or []))
            if u and not str(u).startswith("Selecione")
            and u != setor_atual
        ]
        unidade_destino = st.selectbox(
            "Unidade de Destino:",
            ["Selecione a unidade..."] + opcoes_destino,
            key="unidade_destino_saida",
        )
        if unidade_destino != "Selecione a unidade...":
            ok_setores, setores, mensagem_setores = listar_setores_unidade(unidade_destino)
            if ok_setores:
                setor_destino = st.selectbox(
                    "Setor de Destino:",
                    ["Selecione o setor..."] + setores,
                    key="setor_destino_saida",
                )
            else:
                st.warning(mensagem_setores)

    st.text_area("Observações / Justificativa:", placeholder="Descreva os detalhes da saída...", key="observacoes_saida")

    st.subheader("2. Identificação do Equipamento")
    codigo_saida = st.text_input("Bipe ou digite o código de patrimônio para saída:", placeholder="Aguardando bipagem...")

    if st.button("🚨 Registrar Saída de Equipamento", type="primary", use_container_width=True):
        if codigo_saida.strip():
            usuario = str(st.session_state.get("usuario_logado", "")).strip().lower()
            if motivo == "Transferência para outra Unidade":
                if not unidade_destino or unidade_destino == "Selecione a unidade..." or not setor_destino or setor_destino == "Selecione o setor...":
                    st.warning("Selecione a unidade e o setor de destino antes de confirmar.")
                    return
                ok, _, mensagem = transferir_patrimonio(
                    codigo_saida.strip(),
                    setor_atual,
                    unidade_destino,
                    setor_destino,
                    motivo=motivo,
                    observacao=st.session_state.get("observacoes_saida", ""),
                    usuario=usuario,
                )
            else:
                ok, _, mensagem = registrar_movimentacao_patrimonio(
                    codigo_saida.strip(),
                    "SAIDA",
                    setor_atual,
                    motivo=motivo,
                    observacao=st.session_state.get("observacoes_saida", ""),
                    usuario=usuario,
                )
            if ok:
                st.success(f"Saída do patrimônio `{codigo_saida.strip()}` registrada no PostgreSQL para **{setor_atual}**.")
            else:
                st.error(mensagem)
        else:
            st.warning("Informe ou bipe o código do equipamento antes de confirmar.")