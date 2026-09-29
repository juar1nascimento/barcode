import streamlit as st
from postgresql_persistencia import listar_unidades_setores, formatar_localizacao, registrar_movimentacao

def renderizar_card_saida(lista_urs, lista_ubs):
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📤 Saída de Equipamentos</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Controle transferências, manutenção, recolhimento e baixas.</p>", unsafe_allow_html=True)
        if st.button("📂 Abrir Saída nesta Aba", use_container_width=True, type="primary", key="btn_saida"):
            st.session_state.pagina_atual = "saida"
            st.rerun()

def renderizar_sistema_saida():
    st.title("📤 Saída de Equipamentos - GTI-SESA")
    st.markdown("Registre a movimentação do patrimônio a partir da sua localização atual.")
    st.divider()

    locais = listar_unidades_setores()
    if not locais:
        st.error("Nenhuma unidade/setor ativo foi encontrado no PostgreSQL.")
        return

    motivo = st.selectbox(
        "Motivo da saída",
        [
            "Transferência para outra Unidade",
            "Envio para Manutenção / Conserto",
            "Recolhimento / Desfazimento (Baixa)",
            "Outro",
        ],
        key="saida_motivo",
    )

    destino = None
    if motivo == "Transferência para outra Unidade":
        opcoes = [formatar_localizacao(x) for x in locais]
        destino_label = st.selectbox("📍 Unidade e setor de destino", opcoes, key="saida_destino")
        destino = locais[opcoes.index(destino_label)]

    codigo = st.text_input(
        "Código ou Número de Patrimônio",
        placeholder="Bipe ou digite o patrimônio...",
        key="saida_codigo",
    )
    observacao = st.text_area("Observações / Justificativa", key="saida_observacao")

    usuario = str(st.session_state.get("usuario_logado", "")).strip()
    if not usuario:
        st.warning("Usuário autenticado não identificado.")
        return

    tipo = "TRANSFERENCIA" if destino else "SAIDA"

    if st.button("🚨 Registrar Movimentação", type="primary", use_container_width=True, key="confirmar_saida"):
        if not codigo.strip():
            st.warning("Informe ou bipe o patrimônio antes de confirmar.")
            return

        ok, movimento_id, mensagem = registrar_movimentacao(
            codigo_patrimonio=codigo,
            tipo=tipo,
            usuario=usuario,
            unidade_destino_id=destino["unidade_id"] if destino else None,
            setor_destino_id=destino["setor_id"] if destino else None,
            motivo=motivo,
            observacao=observacao,
        )
        if ok:
            st.success(f"{mensagem} ID da movimentação: {movimento_id}.")
            st.session_state.saida_codigo = ""
        else:
            st.error(mensagem)
