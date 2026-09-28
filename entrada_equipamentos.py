import streamlit as st

from postgresql_persistencia import listar_setores_unidade, registrar_entrada_patrimonio

def renderizar_card_entrada(lista_urs, lista_ubs, navegar_entrada=None):
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📥 Entrada de Equipamentos</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Acesse a ferramenta de registro e recebimento de equipamentos nas unidades.</p>", unsafe_allow_html=True)
        with st.container(horizontal=True, wrap=True, gap="small"):
            urs_entrada = st.selectbox("URS - Unidade Regional de Saúde", lista_urs, key="sel_urs_entrada")
            ubs_entrada = st.selectbox("UBS - Unidade Básica de Saúde", lista_ubs, key="sel_ubs_entrada")
        if st.button("📂 Abrir Entrada nesta Aba", use_container_width=True, type="primary", key="btn_entrada"):
            selecionada = urs_entrada if urs_entrada != "Selecione uma URS..." else (ubs_entrada if ubs_entrada != "Selecione uma UBS..." else "")
            if not selecionada:
                st.warning("⚠️ Selecione a unidade antes de continuar.")
                return
            st.session_state["saved_setor_entrada"] = selecionada
            if navegar_entrada is not None:
                navegar_entrada()
            else:
                st.rerun()


def atualizar_numero_patrimonio():
    """Sincroniza o número lido pelo leitor no campo 'Número de Patrimônio'"""
    st.session_state.numero_patrimonio_val = st.session_state.input_bip_patrimonio


def renderizar_sistema_entrada():
    st.title("📥 Entrada de Equipamentos - GTI-SESA")
    st.markdown("Módulo para registro de recebimento e alocação de novos equipamentos nas unidades.")
    st.divider()
    
    if "numero_patrimonio_val" not in st.session_state:
        st.session_state.numero_patrimonio_val = ""

    setor_atual = st.session_state.get("saved_setor_entrada", "Unidade não selecionada")
    st.info(f"📍 Unidade de Destino Selecionada: **{setor_atual}**")
    
    st.subheader("1. Informações do Recebimento")
    ok_setores, setores, mensagem_setores = listar_setores_unidade(setor_atual)
    if not ok_setores:
        st.error(mensagem_setores)
        return
    setor_destino = st.selectbox("Setor de destino:", setores, key="setor_destino_entrada")
    with st.container(horizontal=True, wrap=True, gap="medium", vertical_alignment="top"):
        c1 = st.container(width="stretch")
        c2 = st.container(width="stretch")
    with c1:
        # Texto atualizado para 'Número de Patrimônio:'
        num_patrimonio = st.text_input(
            "Número de Patrimônio:", 
            value=st.session_state.numero_patrimonio_val, 
            placeholder="Aguardando bipagem ou digitação...", 
            key="input_num_patrimonio"
        )
        # Texto atualizado para 'Setor de origem:'
        setor_origem = st.text_input("Setor de origem:", placeholder="Ex: Almoxarifado Central")
        
    with c2:
        tipo_exibicao = st.selectbox(
            "Tipo de Equipamento:",
            ["Computador (Desktop)", "Monitor/Tela", "Teclado", "Mouse", "Impressora", "Outros"],
            key="tipo_entrada",
        )
        fabricante = st.text_input("Fabricante:", key="fabricante_entrada")
        st.date_input("Data de Recebimento", key="data_entrada")

    st.subheader("2. Código de Patrimônio do Equipamento")
    # Dispara atualização automática do campo 'Número de Patrimônio' ao bipar
    codigo_entrada = st.text_input(
        "Bipe ou digite o código do patrimônio:", 
        placeholder="Aguardando bipagem...", 
        key="input_bip_patrimonio",
        on_change=atualizar_numero_patrimonio
    )
    
    if st.button("✅ Confirmar Entrada de Equipamento", type="primary", use_container_width=True):
        valor_final = num_patrimonio.strip() or codigo_entrada.strip()
        if valor_final:
            usuario = str(st.session_state.get("usuario_logado", "")).strip().lower()
            mapa_tipo = {
                "Computador (Desktop)": "CPU",
                "Monitor/Tela": "Monitores",
                "Teclado": "Teclado",
                "Mouse": "Mouse",
                "Impressora": "Imprenssoras",
                "Outros": "Outros Dispositivos",
            }
            ok, _, mensagem = registrar_entrada_patrimonio(
                numero_patrimonio=valor_final,
                codigo_barras=codigo_entrada.strip(),
                tipo=mapa_tipo[tipo_exibicao],
                unidade=setor_atual,
                setor=setor_destino,
                fabricante=fabricante,
                observacao=str(setor_origem or "").strip(),
                usuario=usuario,
            )
            if ok:
                st.success(f"Entrada do patrimônio `{valor_final}` registrada no PostgreSQL para **{setor_atual}**.")
                st.session_state.numero_patrimonio_val = ""
            else:
                st.error(mensagem)
        else:
            st.warning("Informe ou bipe o código do equipamento antes de confirmar.")