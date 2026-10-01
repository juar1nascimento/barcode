import streamlit as st
from postgresql_persistencia import buscar_patrimonio_detalhado, listar_historico_movimentacoes, formatar_localizacao

def renderizar_historico_movimentacoes():
    st.title("🧾 Histórico de Movimentações")
    st.caption("Auditoria do ciclo de vida de cada patrimônio no PostgreSQL.")
    codigo = st.text_input("Código ou número do patrimônio", placeholder="Bipe ou digite o patrimônio...", key="historico_codigo")
    if not codigo.strip():
        st.info("Informe um patrimônio para consultar seu histórico.")
        return
    patrimonio = buscar_patrimonio_detalhado(codigo, incluir_inativos=True)
    if not patrimonio:
        st.error("Patrimônio não encontrado.")
        return
    local = {"unidade":patrimonio["unidade"],"setor":patrimonio["setor"],
             "numero_consultorio":patrimonio["numero_consultorio"],
             "especialidade":patrimonio["especialidade"]}
    st.success(f"Patrimônio: {patrimonio['numero_patrimonio']} • {patrimonio['tipo']}")
    st.write(f"**Localização atual:** {formatar_localizacao(local)}")
    st.write(f"**Fabricante:** {patrimonio['fabricante'] or 'Não informado'}")
    movimentos = listar_historico_movimentacoes(codigo)
    if not movimentos:
        st.info("Nenhuma movimentação registrada para este patrimônio.")
        return
    st.subheader(f"📜 {len(movimentos)} movimentação(ões)")
    for mov in movimentos:
        with st.container(border=True):
            data = mov["data"].strftime("%d/%m/%Y %H:%M:%S") if mov["data"] else "Data não informada"
            st.markdown(f"**{mov['tipo']}** · {data} · usuário: `{mov['usuario']}`")
            if mov["origem"]: st.write("**Origem:**", formatar_localizacao(mov["origem"]))
            if mov["destino"]: st.write("**Destino:**", formatar_localizacao(mov["destino"]))
            if mov["motivo"]: st.write("**Motivo:**", mov["motivo"])
            if mov["observacao"]: st.write("**Observação:**", mov["observacao"])
            st.caption(f"ID da movimentação: {mov['id']}")
