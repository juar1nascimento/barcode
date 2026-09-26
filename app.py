import streamlit as st

# Importações dos módulos independentes
from login import renderizar_login
from sistema_inventario import renderizar_card_inventario, renderizar_sistema_inventario
from consultorio_contexto import ativar as ativar_contexto_consultorio, desativar as desativar_contexto_consultorio
from persistencia_dupla import ativar as ativar_persistencia_dupla, desativar as desativar_persistencia_dupla
from auditoria_pre_migracao_postgresql import renderizar_auditoria_pre_migracao
from preflight_supabase_secrets import verificar_secrets_supabase, testar_acesso_storage
from entrada_equipamentos import renderizar_card_entrada, renderizar_sistema_entrada
from saida_equipamentos import renderizar_card_saida, renderizar_sistema_saida

# ==========================================
# CONFIGURAÇÕES DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Controle de Patrimônio - GTI-SESA",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilização Responsiva Mobile
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

# ==========================================
# AUTENTICAÇÃO DE LOGIN
# ==========================================
if not renderizar_login():
    st.stop()

if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "portal"

usuario_logado = str(st.session_state.get("usuario_logado", "")).strip().lower()
admin_configurado = str(st.secrets.get("email", {}).get("admin_email", "")).strip().lower()
is_admin = bool(usuario_logado and admin_configurado and usuario_logado == admin_configurado)

# ==========================================
# BARRA LATERAL (MENU E LOGOUT)
# ==========================================
with st.sidebar:
    st.markdown("### 👤 Usuário Autenticado")

    if st.session_state.pagina_atual != "portal":
        if st.button("🏠 Voltar ao Portal"):
            st.session_state.pagina_atual = "portal"
            st.rerun()

    if is_admin:
        st.divider()
        st.markdown("### 🔐 Administração")
        if st.button("🔎 Auditoria pré-migração"):
            st.session_state.pagina_atual = "auditoria_pre_migracao"
            st.rerun()
        if st.button("🔐 Preflight Supabase"):
            st.session_state.pagina_atual = "preflight_supabase"
            st.rerun()

    if st.button("🚪 Sair do Sistema"):
        st.session_state.autenticado = False
        st.session_state.usuario_logado = ""
        st.session_state.pagina_atual = "portal"
        st.rerun()

# ==========================================
# ROTEAMENTO DAS PÁGINAS
# ==========================================
lista_urs = [
    "Selecione uma URS...", "URS Boa Vista", "URS Feu Rosa",
    "URS Jacaraípe", "URS Novo Horizonte", "URS Serra Sede", "URS Serra Dourada"
]

lista_almoxarifado = ["Almoxarifado Central SESA"]

lista_ubs = [
    "Selecione uma UBS...", "UBS André Carloni", "UBS Bairro de Fátima", "UBS Feu Rosa",
    "UBS Barcelona", "UBS Barro Branco", "UBS Campinho da Serra", "UBS Carapebus",
    "UBS Carapina Grande", "UBS Central Carapina", "UBS Cidade Continental", "UBS Eldorado",
    "UBS Jardim Carapina", "UBS Jardim Tropical", "UBS José de Anchieta", "UBS Laranjeiras Velha",
    "UBS Manguinhos", "UBS Manoel Plaza", "UBS Nova Almeida", "UBS Nova Carapina I",
    "UBS Nova Carapina II", "UBS Oceania", "UBS Pitanga", "UBS Planalto Serrano (Bloco A)",
    "UBS Planalto Serrano (Bloco B)", "UBS Porto Canoa", "UBS São Diogo", "UBS São Marcos",
    "UBS Taquara I", "UBS Taquara II", "UBS Vila Nova de Colares", "UBS Vista da Serra",
    "UBS Itinerante (atendimento na área rural)"
]

if st.session_state.pagina_atual == "portal":
    st.title("🖥️ Portal de Sistemas GTI-SESA")
    st.markdown("Bem-vindo ao painel central de aplicações. Escolha o sistema que deseja acessar:")
    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        renderizar_card_inventario(lista_urs, lista_ubs, lista_almoxarifado)
        st.write("")
        renderizar_card_entrada(lista_urs, lista_ubs)
        st.write("")
        renderizar_card_saida(lista_urs, lista_ubs)

elif st.session_state.pagina_atual == "inventario":
    # Ativa somente durante a renderização do inventário para restaurar
    # Número + Especialidade quando o setor selecionado for Consultório.
    ativar_contexto_consultorio()
    ativar_persistencia_dupla()
    try:
        renderizar_sistema_inventario()
    finally:
        desativar_persistencia_dupla()
        desativar_contexto_consultorio()

elif st.session_state.pagina_atual == "auditoria_pre_migracao":
    if not is_admin:
        st.error("Acesso não autorizado.")
        st.session_state.pagina_atual = "portal"
        st.stop()
    renderizar_auditoria_pre_migracao()

elif st.session_state.pagina_atual == "preflight_supabase":
    if not is_admin:
        st.error("Acesso não autorizado.")
        st.session_state.pagina_atual = "portal"
        st.stop()

    st.title("🔐 Preflight seguro do Supabase")
    st.caption("Esta tela não exibe nem registra credenciais.")

    status = verificar_secrets_supabase()
    for item, ok in status.items():
        st.write(("✅ " if ok else "❌ ") + item.replace("_", " ").capitalize())

    if status["configuracao_pronta"]:
        st.success("Configuração mínima das Secrets está presente.")

        if st.button("🔎 Testar acesso somente leitura ao Storage"):
            ok_storage, mensagem_storage = testar_acesso_storage()
            if ok_storage:
                st.success(mensagem_storage)
            else:
                st.error(mensagem_storage)

        st.info(
            "Este teste somente consulta o bucket patrimônio-fotos. "
            "Não cria, envia, altera ou exclui arquivos."
        )
    else:
        st.warning("A configuração ainda não está pronta. Nenhuma credencial foi exibida.")

elif st.session_state.pagina_atual == "entrada":
    renderizar_sistema_entrada()

elif st.session_state.pagina_atual == "saida":
    renderizar_sistema_saida()
