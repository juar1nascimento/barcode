import streamlit as st

from movimentacao_inventario import registrar_entrada


def renderizar_card_entrada(lista_urs, lista_ubs):
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📥 Entrada de Equipamentos</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Acesse a ferramenta de registro e recebimento de equipamentos nas unidades.</p>", unsafe_allow_html=True)
        st.write("")

        urs_entrada = st.selectbox("URS - Unidade Regional de Saúde", lista_urs, key="sel_urs_entrada")
        ubs_entrada = st.selectbox("UBS - Unidade Básica de Saúde", lista_ubs, key="sel_ubs_entrada")
        if urs_entrada != "Selecione uma URS...":
            st.session_state.saved_setor = urs_entrada
        elif ubs_entrada != "Selecione uma UBS...":
            st.session_state.saved_setor = ubs_entrada

        st.write("")
        if st.button("📂 Abrir Entrada nesta Aba", use_container_width=True, type="primary", key="btn_entrada"):
            st.session_state.pagina_atual = "entrada"
            st.rerun()


def atualizar_numero_patrimonio():
    st.session_state.numero_patrimonio_val = st.session_state.input_bip_patrimonio


def renderizar_sistema_entrada():
    st.title("📥 Entrada de Equipamentos - GTI-SESA")
    st.markdown("Módulo para registro de recebimento e alocação de novos equipamentos nas unidades.")
    st.divider()

    st.session_state.setdefault("numero_patrimonio_val", "")
    unidade_atual = st.session_state.get("saved_setor", "")
    st.info(f"📍 Unidade de Destino Selecionada: **{unidade_atual or 'Nenhuma unidade selecionada'}**")

    st.subheader("1. Informações do Recebimento")
    c1, c2 = st.columns(2)
    with c1:
        num_patrimonio = st.text_input("Número de Patrimônio:", value=st.session_state.numero_patrimonio_val, placeholder="Aguardando bipagem ou digitação...", key="input_num_patrimonio")
        setor_destino = st.text_input("Setor de destino:", placeholder="Ex: Farmácia, Recepção, Almoxarifado", key="entrada_setor_destino")
    with c2:
        tipo_equipamento = st.selectbox("Tipo de Equipamento:", ["Computador (Desktop)", "Monitor/Tela", "Nobreak", "Impressora", "Outros"], key="entrada_tipo")
        data_recebimento = st.date_input("Data de Recebimento", key="entrada_data")

    setor_origem = st.text_input("Setor de origem:", placeholder="Ex: Almoxarifado Central", key="entrada_setor_origem")

    st.subheader("2. Código de Patrimônio do Equipamento")
    codigo_entrada = st.text_input("Bipe ou digite o código do patrimônio:", placeholder="Aguardando bipagem...", key="input_bip_patrimonio", on_change=atualizar_numero_patrimonio)
    fabricante = st.text_input("Fabricante:", placeholder="Ex: Dell, HP, Lenovo...", key="entrada_fabricante")

    if st.button("✅ Confirmar Entrada de Equipamento", type="primary", use_container_width=True, key="btn_confirmar_entrada"):
        valor_final = codigo_entrada.strip() or num_patrimonio.strip()
        if not valor_final:
            st.warning("Informe ou bipe o código do equipamento antes de confirmar.")
        elif not unidade_atual:
            st.warning("Selecione uma unidade no Portal antes de registrar a entrada.")
        elif not setor_destino.strip():
            st.warning("Informe o setor de destino do equipamento.")
        else:
            sucesso, mensagem = registrar_entrada(valor_final, tipo_equipamento, unidade_atual, setor_destino.strip(), num_patrimonio.strip(), fabricante.strip(), setor_origem.strip(), data_recebimento)
            if sucesso:
                st.session_state.numero_patrimonio_val = ""
                st.session_state.mensagem_entrada = f"Código `{valor_final}` registrado em **{unidade_atual} / {setor_destino.strip()}**."
                st.rerun()
            else:
                st.error(mensagem)

    mensagem = st.session_state.pop("mensagem_entrada", None)
    if mensagem:
        st.success(f"✅ Entrada registrada com sucesso. {mensagem}")
