import streamlit as st

from inventario_regras import setores_menu, tipos_patrimonio_menu, normalizar_setor, normalizar_fabricante
from servicos.movimentacao import registrar_entrada


def renderizar_card_entrada(lista_urs, lista_ubs):
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📥 Entrada de Equipamentos</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Acesse a ferramenta de registro e recebimento de equipamentos nas unidades.</p>", unsafe_allow_html=True)
        st.write("")
        urs_entrada = st.selectbox("URS - Unidade Regional de Saúde", lista_urs, index=None, placeholder="Selecione uma URS...", key="sel_urs_entrada")
        ubs_entrada = st.selectbox("UBS - Unidade Básica de Saúde", lista_ubs, index=None, placeholder="Selecione uma UBS...", key="sel_ubs_entrada")
        unidade_escolhida = urs_entrada if urs_entrada else (ubs_entrada if ubs_entrada else "")
        st.write("")
        if st.button("📂 Abrir Entrada nesta Aba", use_container_width=True, type="primary", key="btn_entrada"):
            if not unidade_escolhida:
                st.warning("Selecione uma URS ou UBS válida para continuar.")
            else:
                st.session_state.unidade_entrada_selecionada = unidade_escolhida
                st.session_state.pagina_atual = "entrada"
                st.rerun()


def atualizar_numero_patrimonio():
    st.session_state.numero_patrimonio_val = st.session_state.input_bip_patrimonio


def renderizar_sistema_entrada():
    st.title("📥 Entrada de Equipamentos - GTI-SESA")
    st.markdown("Módulo para registro de recebimento e alocação de novos equipamentos nas unidades.")
    st.divider()
    st.session_state.setdefault("numero_patrimonio_val", "")
    unidade_atual = st.session_state.get("unidade_entrada_selecionada", "")
    if not unidade_atual:
        st.warning("Selecione uma unidade no Portal antes de registrar a entrada.")
        return
    st.info(f"📍 Unidade de Destino Selecionada: **{unidade_atual}**")
    st.subheader("1. Informações do Recebimento")
    c1, c2 = st.columns(2)
    with c1:
        num_patrimonio = st.text_input("Número de Patrimônio:", value=st.session_state.numero_patrimonio_val, placeholder="Aguardando bipagem ou digitação...", key="input_num_patrimonio")
        setor_destino = st.selectbox("Setor de destino:", setores_menu(), index=None, placeholder="Selecione um setor...", key="entrada_setor_destino")
        setor_destino_custom = ""
        if setor_destino == "Outro Setor":
            setor_destino_custom = st.text_input("Nome do Setor:", placeholder="Digite o nome do setor...", key="entrada_setor_destino_custom")
    with c2:
        tipo_equipamento = st.selectbox("Tipo de Equipamento:", tipos_patrimonio_menu(), index=None, placeholder="Selecione o tipo de patrimônio...", key="entrada_tipo")
        data_recebimento = st.date_input("Data de Recebimento", key="entrada_data")
    setor_origem = st.text_input("Setor de origem:", placeholder="Ex: Almoxarifado Central", key="entrada_setor_origem")
    st.subheader("2. Código de Patrimônio do Equipamento")
    codigo_entrada = st.text_input("Bipe ou digite o código do patrimônio:", placeholder="Aguardando bipagem...", key="input_bip_patrimonio", on_change=atualizar_numero_patrimonio)
    fabricante = st.text_input("Fabricante:", placeholder="Ex: Dell, HP, Lenovo...", key="entrada_fabricante")
    setor_final = setor_destino_custom.strip() if setor_destino == "Outro Setor" else normalizar_setor(setor_destino or "")
    fabricante_final = normalizar_fabricante(fabricante.strip())
    if st.button("✅ Confirmar Entrada de Equipamento", type="primary", use_container_width=True, key="btn_confirmar_entrada"):
        valor_final = codigo_entrada.strip() or num_patrimonio.strip()
        if not valor_final:
            st.warning("Informe ou bipe o código do equipamento antes de confirmar.")
        elif not setor_final:
            st.warning("Selecione ou informe o setor de destino do equipamento.")
        elif not tipo_equipamento:
            st.warning("Selecione o tipo de patrimônio do equipamento.")
        else:
            sucesso, mensagem = registrar_entrada(valor_final, tipo_equipamento, unidade_atual, setor_final, num_patrimonio.strip(), fabricante_final, setor_origem.strip(), data_recebimento)
            if sucesso:
                st.session_state.numero_patrimonio_val = ""
                st.session_state.mensagem_entrada = f"Código `{valor_final}` registrado em **{unidade_atual} / {setor_final}**."
                st.rerun()
            else:
                st.error(mensagem)
    mensagem = st.session_state.pop("mensagem_entrada", None)
    if mensagem:
        st.success(f"✅ Entrada registrada com sucesso. {mensagem}")
