import streamlit as st

from login import renderizar_login
from modulos.sistema_inventarios import renderizar_card_inventario, renderizar_sistema_inventario
from modulos.entrada_equipamentos import renderizar_card_entrada, renderizar_sistema_entrada
from modulos.saida_equipamentos import renderizar_card_saida, renderizar_sistema_saida
from Tabela_de_dados_Inventario_7_2 import LISTA_URS_PADRAO, LISTA_UBS_PADRAO

st.set_page_config(page_title="Controle de Patrimônio - GTI-SESA", page_icon="📦", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
        @media (max-width: 768px) {
            .main .block-container { padding-left: 0.6rem !important; padding-right: 0.6rem !important; padding-top: 1rem !important; }
            h1 { font-size: 1.5rem !important; text-align: center; }
            input, select, textarea { font-size: 16px !important; }
            .stButton > button, .stDownloadButton > button { width: 100% !important; min-height: 48px !important; font-size: 16px !important; font-weight: bold !important; }
        }
        .scanner-wrapper { width: 100%; max-width: 100%; margin: auto; }
    </style>
""", unsafe_allow_html=True)

if not renderizar_login():
    st.stop()

if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "portal"

with st.sidebar:
    st.markdown("### 👤 Usuário Autenticado")
    if st.session_state.pagina_atual != "portal":
        if st.button("🏠 Voltar ao Portal"):
            st.session_state.pagina_atual = "portal"
            st.rerun()
    if st.button("🚪 Sair do Sistema"):
        st.session_state.autenticado = False
        st.session_state.pagina_atual = "portal"
        st.rerun()

lista_urs = list(LISTA_URS_PADRAO)
lista_ubs = list(LISTA_UBS_PADRAO)

if st.session_state.pagina_atual == "portal":
    st.title("🖥️ Portal de Sistemas GTI-SESA")
    st.markdown("Bem-vindo ao painel central de aplicações. Escolha o sistema que deseja acessar:")
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        renderizar_card_inventario(lista_urs, lista_ubs)
        st.write("")
        renderizar_card_entrada(lista_urs, lista_ubs)
        st.write("")
        renderizar_card_saida(lista_urs, lista_ubs)
elif st.session_state.pagina_atual == "inventario":
    renderizar_sistema_inventario()
elif st.session_state.pagina_atual == "entrada":
    renderizar_sistema_entrada()
elif st.session_state.pagina_atual == "saida":
    renderizar_sistema_saida()
