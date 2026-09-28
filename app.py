import streamlit as st

# Importações dos módulos independentes
from login import renderizar_login
from sistema_inventario import renderizar_card_inventario, renderizar_sistema_inventario
from consultorio_contexto import ativar as ativar_contexto_consultorio, desativar as desativar_contexto_consultorio
from persistencia_dupla import ativar as ativar_persistencia_dupla, desativar as desativar_persistencia_dupla
from auditoria_pre_migracao_postgresql import renderizar_auditoria_pre_migracao
from preflight_supabase_secrets import verificar_secrets_supabase, testar_acesso_storage
from teste_upload_foto import renderizar_teste_upload_foto
from Tabela_de_dados_Inventario_7_2 import renderizar_auditoria_reconciliacao
from entrada_equipamentos import renderizar_card_entrada, renderizar_sistema_entrada
from saida_equipamentos import renderizar_card_saida, renderizar_sistema_saida

# ==========================================
# CONFIGURAÇÕES DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Controle de Patrimônio - GTI-SESA",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="auto"
)

# Estilização Responsiva Mobile
st.markdown("""
    <style>
        @media (max-width: 768px) {
            .main .block-container {
                padding-left: 0.65rem !important;
                padding-right: 0.65rem !important;
                padding-top: 0.75rem !important;
                max-width: 100% !important;
            }
            h1 { font-size: 1.45rem !important; line-height: 1.2 !important; }
            h2 { font-size: 1.25rem !important; }
            h3 { font-size: 1.1rem !important; }
            input, select, textarea { font-size: 16px !important; }
            .stButton > button, .stDownloadButton > button {
                width: 100% !important;
                min-height: 48px !important;
                font-size: 16px !important;
                font-weight: 600 !important;
            }
            [data-testid="stHorizontalBlock"] { gap: 0.55rem !important; }
            [data-testid="stMetric"] { padding: 0.5rem !important; }
            [data-testid="stDataFrame"] { max-width: 100% !important; }
            section[data-testid="stSidebar"] { width: min(92vw, 360px) !important; }
        }
        .scanner-wrapper { width: 100%; max-width: 100%; margin: auto; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# AUTENTICAÇÃO DE LOGIN
# ==========================================
if not renderizar_login():
    st.stop()

usuario_logado = str(st.session_state.get("usuario_logado", "")).strip().lower()
admin_configurado = str(st.secrets.get("email", {}).get("admin_email", "")).strip().lower()
is_admin = bool(usuario_logado and admin_configurado and usuario_logado == admin_configurado)

reconciliacao_pendente = bool(st.session_state.get("reconciliacao_pendente"))

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

# ==========================================
# PÁGINAS E NAVEGAÇÃO
# ==========================================
def _pagina_portal():
    with st.container(width="stretch"):
        renderizar_card_inventario(
            lista_urs,
            lista_ubs,
            lista_almoxarifado,
            navegar_inventario=lambda: st.switch_page(page_inventario),
        )
        st.write("")
        renderizar_card_entrada(
            lista_urs,
            lista_ubs,
            navegar_entrada=lambda: st.switch_page(page_entrada),
        )
        st.write("")
        renderizar_card_saida(
            lista_urs,
            lista_ubs,
            navegar_saida=lambda: st.switch_page(page_saida),
        )

def _pagina_inventario():
    ativar_contexto_consultorio()
    ativar_persistencia_dupla()
    try:
        renderizar_sistema_inventario(
            navegar_portal=lambda: st.switch_page(page_portal)
        )
    finally:
        desativar_persistencia_dupla()
        desativar_contexto_consultorio()

def _pagina_auditoria_pre_migracao():
    renderizar_auditoria_pre_migracao()

def _pagina_preflight_supabase():
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
        st.error(
            "O ambiente publicado está sem a configuração [supabase]. "
            "A correção deve ser feita nas Secrets do aplicativo, não no código."
        )

        with st.expander("📋 Como corrigir com segurança"):
            st.markdown(
                "No Streamlit Community Cloud, abra **Manage app → Settings → Secrets** "
                "e cadastre o bloco abaixo, substituindo somente os valores de exemplo. "
                "Não envie a chave pelo chat nem para o GitHub."
            )
            st.code(
                '''[supabase]
url = "https://vgabxdprocwmpmhoxrgt.supabase.co"
secret_key = "COLOQUE_A_CHAVE_SECRETA_DO_SUPABASE_AQUI"''',
                language="toml",
            )
            st.markdown(
                "Depois de salvar as Secrets, aguarde o aplicativo reiniciar e volte a esta tela. "
                "O preflight deverá mostrar **4 itens verdes**. Só então faremos o teste de leitura "
                "do bucket e, depois, o primeiro upload controlado."
            )

def _pagina_reconciliacao():
    renderizar_auditoria_reconciliacao()

def _pagina_teste_upload():
    renderizar_teste_upload_foto()

def _pagina_entrada():
    renderizar_sistema_entrada()

def _pagina_saida():
    renderizar_sistema_saida()

page_portal = st.Page(
    _pagina_portal,
    title="Portal",
    icon=":material/home:",
    url_path="portal",
    default=True,
)
page_inventario = st.Page(
    _pagina_inventario,
    title="Inventário",
    icon=":material/inventory_2:",
    url_path="inventario",
)
page_entrada = st.Page(
    _pagina_entrada,
    title="Entrada",
    icon=":material/input:",
    url_path="entrada",
)
page_saida = st.Page(
    _pagina_saida,
    title="Saída",
    icon=":material/output:",
    url_path="saida",
)
page_auditoria = st.Page(
    _pagina_auditoria_pre_migracao,
    title="Auditoria pré-migração",
    icon=":material/search:",
    url_path="auditoria-pre-migracao",
)
page_preflight = st.Page(
    _pagina_preflight_supabase,
    title="Preflight Supabase",
    icon=":material/security:",
    url_path="preflight-supabase",
)
page_reconciliacao = st.Page(
    _pagina_reconciliacao,
    title="Reconciliação Sheets × PostgreSQL",
    icon=":material/sync:",
    url_path="reconciliacao",
)
page_teste_upload = st.Page(
    _pagina_teste_upload,
    title="Teste upload de foto",
    icon=":material/photo_camera:",
    url_path="teste-upload-foto",
)

paginas = [page_portal, page_inventario, page_entrada, page_saida]
if is_admin:
    paginas += [
        page_auditoria,
        page_preflight,
        page_reconciliacao,
        page_teste_upload,
    ]

pg = st.navigation(paginas, position="hidden")
pagina_url_atual = getattr(pg, "url_path", "portal")

# ==========================================
# BARRA LATERAL (MENU E LOGOUT)
# ==========================================
with st.sidebar:
    st.markdown("### 👤 Usuário Autenticado")

    if pagina_url_atual != page_portal.url_path:
        if st.button("🏠 Voltar ao Portal"):
            st.switch_page(page_portal)

    if is_admin and reconciliacao_pendente:
        st.warning("⚠️ Há uma persistência no PostgreSQL aguardando confirmação/reconciliação no Google Sheets.")
        if st.button("🔄 Abrir reconciliação pendente"):
            st.switch_page(page_reconciliacao)

    if is_admin:
        st.divider()
        st.markdown("### 🔐 Administração")
        if st.button("🔎 Auditoria pré-migração"):
            st.switch_page(page_auditoria)
        if st.button("🔐 Preflight Supabase"):
            st.switch_page(page_preflight)
        if st.button("🧪 Teste upload de foto"):
            st.switch_page(page_teste_upload)
        if st.button("🔄 Reconciliação Sheets × PostgreSQL"):
            st.switch_page(page_reconciliacao)

    if st.button("🚪 Sair do Sistema"):
        st.session_state.autenticado = False
        st.session_state.usuario_logado = ""
        st.session_state.pagina_atual = "portal"
        st.rerun()

# A execução da página selecionada fica sob controle da arquitetura
# st.Page/st.navigation. O layout e os componentes das páginas existentes
# permanecem nos módulos originais.
pg.run()
