import streamlit as st
from postgresql_persistencia import (
    conectar, listar_unidades_setores, formatar_localizacao,
    registrar_movimentacao,
)

def renderizar_card_entrada(lista_urs, lista_ubs):
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📥 Entrada de Equipamentos</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Registre a entrada e localização de equipamentos.</p>", unsafe_allow_html=True)
        if st.button("📂 Abrir Entrada nesta Aba", use_container_width=True, type="primary", key="btn_entrada"):
            st.session_state.pagina_atual = "entrada"
            st.rerun()

def renderizar_sistema_entrada():
    st.title("📥 Entrada de Equipamentos - GTI-SESA")
    st.markdown("Registre uma entrada para um patrimônio já cadastrado e atualize sua localização.")
    st.divider()

    locais = listar_unidades_setores()
    if not locais:
        st.error("Nenhuma unidade/setor ativo foi encontrado no PostgreSQL.")
        return

    opcoes = [formatar_localizacao(x) for x in locais]
    destino_label = st.selectbox("📍 Unidade e setor de destino", opcoes, key="entrada_destino")
    destino = locais[opcoes.index(destino_label)]

    codigo = st.text_input(
        "Código ou Número de Patrimônio",
        placeholder="Bipe ou digite o código...",
        key="entrada_codigo",
    )
    motivo = st.text_input("Motivo da entrada", value="Recebimento de equipamento", key="entrada_motivo")
    observacao = st.text_area("Observações", key="entrada_observacao")

    usuario = str(st.session_state.get("usuario_logado", "")).strip()
    if not usuario:
        st.warning("Usuário autenticado não identificado.")
        return

    if st.button("✅ Confirmar Entrada", type="primary", use_container_width=True, key="confirmar_entrada"):
        if not codigo.strip():
            st.warning("Informe ou bipe o patrimônio antes de confirmar.")
            return

        ok, movimento_id, mensagem = registrar_movimentacao(
            codigo_patrimonio=codigo,
            tipo="ENTRADA",
            usuario=usuario,
            unidade_destino_id=destino["unidade_id"],
            setor_destino_id=destino["setor_id"],
            motivo=motivo,
            observacao=observacao,
        )
        if ok:
            st.success(f"{mensagem} ID da movimentação: {movimento_id}.")
            st.session_state.entrada_codigo = ""
        else:
            st.error(mensagem)
