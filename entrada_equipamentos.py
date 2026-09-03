import streamlit as st

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

def renderizar_sistema_entrada():
    st.title("📥 Entrada de Equipamentos - GTI-SESA")
    st.markdown("Módulo para registro de recebimento e alocação de novos equipamentos nas unidades.")
    st.divider()
    
    setor_atual = st.session_state.get("saved_setor", "Unidade não selecionada")
    st.info(f"📍 Unidade de Destino Selecionada: **{setor_atual}**")
    
    st.subheader("1. Informações do Recebimento")
    c1, c2 = st.columns(2)
    with c1:
        st.text_input("Número da Nota Fiscal / Termo:", placeholder="Ex: NF-12345")
        st.text_input("Fornecedor / Origem:", placeholder="Ex: Almoxarifado Central")
    with c2:
        st.selectbox("Tipo de Equipamento:", ["Computador (Desktop)", "Monitor/Tela", "Nobreak", "Impressora", "Outros"])
        st.date_input("Data de Recebimento")

    st.subheader("2. Código de Patrimônio do Equipamento")
    codigo_entrada = st.text_input("Bipe ou digite o código do patrimônio:", placeholder="Aguardando bipagem...")
    
    if st.button("✅ Confirmar Entrada de Equipamento", type="primary", use_container_width=True):
        if codigo_entrada.strip():
            st.success(f"Equipamento `{codigo_entrada.strip()}` registrado com sucesso no setor **{setor_atual}**!")
        else:
            st.warning("Informe ou bipe o código do equipamento antes de confirmar.")