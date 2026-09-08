import base64
import json
import os
import hashlib
import re
import smtplib
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import streamlit as st

# Logotipo vetorial otimizado da Prefeitura Municipal da Serra.
# Mantém o brasão e reorganiza a tipografia para reproduzir a proporção
# visual da referência enviada, sem perda de qualidade em telas de alta resolução.
LOGO_SERRA_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 160" role="img" aria-label="Prefeitura Municipal da Serra"><defs><linearGradient id="verde" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1f9848"/><stop offset="1" stop-color="#16753a"/></linearGradient></defs><g transform="translate(0,2)"><path d="M12 10H148C148 92 133 135 80 153C27 135 12 92 12 10Z" fill="url(#verde)" stroke="#125f31" stroke-width="2"/><path d="M25 23H135V48H25Z" fill="#18823e"/><path d="M25 23H135C135 88 121 125 80 142C39 125 25 88 25 23Z" fill="#fff"/><path d="M25 23H135V48H25Z" fill="#18823e"/><text x="80" y="42" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="14" font-weight="700" fill="#fff">SERRA</text><text x="45" y="42" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="7" fill="#fff">1535</text><text x="115" y="42" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="7" fill="#fff">1822</text><text x="32" y="42" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="9" fill="#fff">★</text><text x="128" y="42" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="9" fill="#fff">★</text><circle cx="80" cy="70" r="15" fill="none" stroke="#111" stroke-width="3.5" stroke-dasharray="5,4"/><circle cx="80" cy="70" r="10" fill="#fbd100" stroke="#111" stroke-width="1.3"/><path d="M74 77V67H82L80 63L86 63L84 67V77Z" fill="#111"/><rect x="42" y="91" width="76" height="10" rx="1" fill="#111"/><rect x="47" y="87" width="8" height="4" fill="#111"/><rect x="59" y="87" width="8" height="4" fill="#111"/><rect x="71" y="87" width="8" height="4" fill="#111"/><rect x="83" y="87" width="8" height="4" fill="#111"/><rect x="95" y="87" width="8" height="4" fill="#111"/><rect x="107" y="87" width="8" height="4" fill="#111"/><path d="M40 133H120C120 120 40 120 40 133Z" fill="#fbd100"/><path d="M80 103V119M65 106L72 120M95 106L88 120M53 113L65 123M107 113L95 123" stroke="#fbd100" stroke-width="2"/><path d="M33 136Q50 120 65 133Q80 116 95 136Q110 123 127 136V141C115 149 45 149 33 141Z" fill="#2d8647" stroke="#1e5c30"/><path d="M36 141Q80 156 124 141C110 154 50 154 36 141Z" fill="#1b4d89"/><text x="35" y="101" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="8" fill="#fff">★</text><text x="125" y="101" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="8" fill="#fff">★</text><text x="80" y="150" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="8" fill="#fff">★</text></g><g fill="#111"><text x="170" y="48" font-family="Arial,Helvetica,sans-serif" font-size="20" font-weight="400" letter-spacing="0.6">PREFEITURA MUNICIPAL DA</text><text x="168" y="116" font-family="Arial Black,Arial,Helvetica,sans-serif" font-size="64" font-weight="900" letter-spacing="-1.2">SERRA</text></g></svg>"""

ADMIN_EMAIL_DEFAULT = "juari.neris@gmail.com"
DB_FILE = "db_usuarios.json"

# -------------------------------------------------------------
# FUNÇÕES DE BANCO DE DADOS LOCAL (JSON) E HASH
# -------------------------------------------------------------
def hash_senha(senha: str) -> str:
    """Gera hash SHA-256 seguro da senha."""
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()

def carregar_usuarios() -> dict:
    """Carrega a base de dados de usuários de db_usuarios.json."""
    if not os.path.exists(DB_FILE):
        default_db = {
            ADMIN_EMAIL_DEFAULT.lower(): {
                "senha": hash_senha("serra123"),
                "aprovado": True
            }
        }
        salvar_usuarios(default_db)
        return default_db
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def salvar_usuarios(db: dict):
    """Salva a base de dados atualizada no arquivo JSON."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

# -------------------------------------------------------------
# FUNÇÕES DE VALIDAÇÃO E E-MAIL
# -------------------------------------------------------------
def validar_email(email: str) -> bool:
    """Valida formato padrão de e-mail."""
    padrao = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return bool(re.match(padrao, email.strip()))

def validar_senha_alfanumerica_8(senha: str) -> tuple[bool, str]:
    """Garante que a senha possua exatamente 8 caracteres alfanuméricos."""
    if len(senha) != 8:
        return False, "A senha deve conter exatamente 8 caracteres."
    if not senha.isalnum():
        return False, "A senha deve ser alfanumérica (apenas letras e números, sem símbolos)."
    if not (any(c.isalpha() for c in senha) and any(c.isdigit() for c in senha)):
        return False, "A senha deve conter ao menos uma letra e um número."
    return True, ""

def enviar_email(destinatario: str, assunto: str, corpo_html: str) -> tuple[bool, str]:
    """Dispara e-mail via SMTP configurado nas secrets do Streamlit."""
    try:
        email_secrets = st.secrets.get("email", {})
        smtp_server = email_secrets.get("smtp_server", "smtp.gmail.com")
        smtp_port = int(email_secrets.get("smtp_port", 587))
        sender_email = email_secrets.get("sender_email", "")
        sender_password = email_secrets.get("sender_password", "")

        if not sender_email or not sender_password:
            return False, "Credenciais SMTP não configuradas nas Secrets."

        msg = MIMEMultipart("alternative")
        msg["From"] = sender_email
        msg["To"] = destinatario
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo_html, "html"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, destinatario, msg.as_string())

        return True, "E-mail enviado com sucesso."
    except Exception as e:
        return False, f"Erro SMTP: {str(e)}"

def processar_acao_via_url():
    """Captura e processa a aprovação/recusa feita através dos botões no e-mail do admin."""
    params = st.query_params
    if "acao" in params and "usuario" in params:
        acao = params["acao"]
        user_email = params["usuario"].strip().lower()
        st.query_params.clear()

        db = carregar_usuarios()

        if acao == "aprovar":
            if user_email in db:
                db[user_email]["aprovado"] = True
                salvar_usuarios(db)

            corpo = f"""
            <h3>Prefeitura Municipal da Serra</h3>
            <p>Seu cadastro/solicitação de acesso para o e-mail <b>{user_email}</b> foi <b>ACEITO</b> pelo administrador.</p>
            <p>Você já pode acessar o sistema normalmente.</p>
            """
            enviar_email(user_email, "Cadastro Aceito - Prefeitura da Serra", corpo)
            st.success(f"Solicitação do usuário {user_email} foi APROVADA com sucesso!")

        elif acao == "recusar":
            if user_email in db:
                db[user_email]["aprovado"] = False
                salvar_usuarios(db)

            corpo = f"""
            <h3>Prefeitura Municipal da Serra</h3>
            <p>Sua solicitação de cadastro para o e-mail <b>{user_email}</b> foi <b>RECUSADA</b> pelo administrador.</p>
            """
            enviar_email(user_email, "Cadastro Recusado - Prefeitura da Serra", corpo)
            st.error(f"Solicitação do usuário {user_email} foi RECUSADA.")

def renderizar_login() -> bool:
    processar_acao_via_url()

    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False
    if "tela_atual" not in st.session_state:
        st.session_state.tela_atual = "login"
    if st.session_state.autenticado:
        return True

    b64_logo = base64.b64encode(LOGO_SERRA_SVG.encode("utf-8")).decode("ascii")
    logo_html = f'''<div class="login-logo-wrap"><img src="data:image/svg+xml;base64,{b64_logo}" class="login-logo" alt="Prefeitura Municipal da Serra" /></div>'''

    st.markdown("""
        <style>
            .stApp {
                background-color: #f2f4f7 !important;
                background-image:
                    linear-gradient(rgba(242, 244, 247, 0.18), rgba(242, 244, 247, 0.18)),
                    url("https://raw.githubusercontent.com/juar1nascimento/barcode/main/assets/login_background.svg") !important;
                background-size: cover !important;
                background-position: center center !important;
                background-repeat: no-repeat !important;
                background-attachment: fixed !important;
            }
            header, footer, #MainMenu { visibility: hidden; }
            .main .block-container { padding-top: 1.6rem !important; padding-bottom: 2.5rem !important; }
            .login-logo-wrap {
                width: 100%;
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 0 auto 2.15rem auto;
                line-height: 0;
            }
            .login-logo {
                width: 230px;
                height: auto;
                max-width: 78vw;
                display: block;
                image-rendering: auto;
            }
            div[data-testid="stForm"] {
                width: 100% !important;
                max-width: 810px !important;
                margin: 0 auto !important;
                box-sizing: border-box !important;
                background-color: #ffffff !important;
                border: 1px solid #e1e4e8 !important;
                border-radius: 4px !important;
                padding: 35px 40px !important;
                box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
            }
            .login-title {
                text-align: center;
                font-size: 20px;
                line-height: 1.25;
                font-weight: 600;
                color: #24292e;
                margin: 0 0 25px 0;
            }
            button[kind="tertiary"] {
                display: flex !important;
                justify-content: flex-end !important;
                width: 100% !important;
                margin-left: auto !important;
                font-size: 12px !important;
                color: #24292e !important;
                text-decoration: underline !important;
                margin-top: -10px !important;
                margin-bottom: 15px !important;
                padding: 0 !important;
                height: auto !important;
                background: transparent !important;
                border: none !important;
            }
            button[kind="tertiary"] div, button[kind="tertiary"] p {
                justify-content: flex-end !important;
                text-align: right !important;
            }
            div[data-baseweb="input"] {
                background-color: #f4f6f8 !important;
                border: 1px solid #d1d5da !important;
                border-radius: 4px !important;
            }
            div[data-baseweb="select"] > div {
                background-color: #ffffff !important;
                border: 1px solid #d1d5da !important;
                border-radius: 4px !important;
            }
            div[data-baseweb="select"] svg, div[data-baseweb="input"] button svg { transform: scale(0.65) !important; }
            div[data-testid="stForm"] button[kind="secondaryFormSubmit"],
            div[data-testid="stForm"] button[kind="primaryFormSubmit"] {
                background-color: #555555 !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 4px !important;
                height: 42px !important;
                font-size: 14px !important;
                font-weight: 600 !important;
                margin-top: 15px !important;
            }
            div[data-testid="stForm"] button[kind="secondaryFormSubmit"]:hover,
            div[data-testid="stForm"] button[kind="primaryFormSubmit"]:hover {
                background-color: #333333 !important;
                color: #ffffff !important;
            }
            .error-box {
                width: 100%;
                max-width: 810px;
                box-sizing: border-box;
                margin: 15px auto 0 auto;
                background-color: #fdf2f2;
                border: 1px solid #f8b4b4;
                border-left: 4px solid #e02424;
                color: #9b1c1c;
                padding: 12px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            @media (max-width: 768px) {
                .main .block-container { padding-left: 0.75rem !important; padding-right: 0.75rem !important; padding-top: 1rem !important; }
                .login-logo { width: 220px; max-width: 72vw; }
                div[data-testid="stForm"] { max-width: 100% !important; padding: 28px 24px !important; }
                .error-box { max-width: 100%; }
                .stApp { background-attachment: scroll !important; }
            }
        </style>
    """, unsafe_allow_html=True)

    # Coluna central proporcional à referência visual enviada.
    _, col_center, _ = st.columns([0.7, 2.0, 0.7])

    with col_center:
        st.markdown(logo_html, unsafe_allow_html=True)

        if st.session_state.tela_atual == "redefinicao_solicitar":
            with st.form(key="form_solicitar_email", clear_on_submit=False):
                st.markdown('<div class="login-title">Redefinição de senha</div>', unsafe_allow_html=True)
                st.write("**Informe seu e-mail de acesso**")
                email_req = st.text_input("E-mail", value="", placeholder="seuemail@serra.es.gov.br", label_visibility="collapsed", key="email_req")
                btn_enviar_req = st.form_submit_button("Avançar", use_container_width=True)

                if btn_enviar_req:
                    if validar_email(email_req):
                        st.session_state.email_solicitante = email_req.strip().lower()
                        st.session_state.tela_atual = "redefinicao_criar"
                        st.rerun()
                    else:
                        st.error("Por favor, informe um e-mail com formato válido.")

            if st.button("← Voltar ao Login", use_container_width=True, key="btn_voltar_solicitar"):
                st.session_state.tela_atual = "login"
                st.rerun()

        elif st.session_state.tela_atual == "redefinicao_criar":
            with st.form(key="form_criar_usuario", clear_on_submit=False):
                st.markdown('<div class="login-title">Redefinição de senha</div>', unsafe_allow_html=True)
                st.write("**Login de Usuário (Obrigatório ser E-mail)**")
                novo_usuario = st.text_input("Usuário", value=st.session_state.get('email_solicitante', ''), placeholder="usuario@dominio.com", label_visibility="collapsed", key="novo_user")
                st.write("**Nova Senha (Exatamente 8 caracteres alfanuméricos)**")
                nova_senha = st.text_input("Nova Senha", value="", type="password", placeholder="Ex: serra123", label_visibility="collapsed", key="nova_pass")
                st.write("**Confirme a Nova Senha**")
                confirma_senha = st.text_input("Confirmar Senha", value="", type="password", placeholder="Repita a senha", label_visibility="collapsed", key="confirma_pass")
                btn_finalizar = st.form_submit_button("Cadastrar e Solicitar Autorização", use_container_width=True)

                if btn_finalizar:
                    novo_user_clean = novo_usuario.strip().lower()
                    if not validar_email(novo_user_clean):
                        st.error("O nome de usuário deve ser obrigatoriamente um e-mail válido.")
                    elif nova_senha != confirma_senha:
                        st.error("A confirmação de senha não confere com a nova senha digitada.")
                    else:
                        senha_ok, msg_erro = validar_senha_alfanumerica_8(nova_senha)
                        if not senha_ok:
                            st.error(msg_erro)
                        else:
                            db = carregar_usuarios()
                            db[novo_user_clean] = {"senha": hash_senha(nova_senha), "aprovado": False}
                            salvar_usuarios(db)

                            admin_email = st.secrets.get("email", {}).get("admin_email", ADMIN_EMAIL_DEFAULT)
                            app_url = st.secrets.get("email", {}).get("app_url", "http://localhost:8501").rstrip("/")
                            params_aprovar = urllib.parse.urlencode({"acao": "aprovar", "usuario": novo_user_clean})
                            params_recusar = urllib.parse.urlencode({"acao": "recusar", "usuario": novo_user_clean})
                            link_aprovar = f"{app_url}/?{params_aprovar}"
                            link_recusar = f"{app_url}/?{params_recusar}"

                            corpo_admin = f"""
                            <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
                                <h3 style="color: #1b8e42;">Alerta de Novo Usuário / Solicitação de Cadastro</h3>
                                <p>Um novo cadastro/redefinição foi solicitado no sistema:</p>
                                <ul><li><b>E-mail/Usuário Solicitado:</b> {novo_user_clean}</li></ul>
                                <p>Clique em uma das opções abaixo para responder à solicitação diretamente:</p>
                                <div style="margin-top: 25px;">
                                    <a href="{link_aprovar}" style="background-color: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; margin-right: 15px; display: inline-block;">Autorizar Cadastro</a>
                                    <a href="{link_recusar}" style="background-color: #dc3545; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Recusar Cadastro</a>
                                </div>
                            </div>
                            """
                            enviar_email(admin_email, f"Solicitação de Cadastro: {novo_user_clean}", corpo_admin)
                            st.success(f"Solicitação enviada com sucesso! Um e-mail com os botões de autorização foi encaminhado para {admin_email}.")
                            st.session_state.tela_atual = "login"

            if st.button("← Cancelar", use_container_width=True, key="btn_cancelar_criar"):
                st.session_state.tela_atual = "login"
                st.rerun()

        else:
            with st.form(key="glpi_login_form", clear_on_submit=False):
                st.markdown('<div class="login-title">Faça login na sua conta</div>', unsafe_allow_html=True)
                st.write("**Usuário**")
                usuario = st.text_input("Usuário", value="", placeholder="seuemail@serra.es.gov.br", label_visibility="collapsed", key="login_user")
                st.write("**Senha**")
                senha = st.text_input("Senha", value="", type="password", label_visibility="collapsed", key="login_pass")

                if st.form_submit_button("Esqueceu sua senha?", type="tertiary"):
                    st.session_state.tela_atual = "redefinicao_solicitar"
                    st.rerun()

                st.write("**Origem de login**")
                origem = st.selectbox("Origem de login", ["SERRA.LOCAL", "BANCO DE DADOS INTERNO"], label_visibility="collapsed", key="login_domain")
                submit = st.form_submit_button("Entrar", use_container_width=True)

                if submit:
                    user_clean = usuario.strip().lower()
                    if not user_clean or not senha.strip():
                        st.session_state.erro_login_msg = "Uso inválido de ID de sessão ou credenciais incorretas"
                    else:
                        db = carregar_usuarios()
                        if user_clean not in db:
                            st.session_state.erro_login_msg = "Acesso negado: Este e-mail não está cadastrado no sistema"
                        else:
                            dados_user = db[user_clean]
                            if not dados_user.get("aprovado", False):
                                st.session_state.erro_login_msg = "Seu e-mail está cadastrado, porém ainda aguarda AUTORIZAÇÃO do administrador"
                            elif dados_user.get("senha") != hash_senha(senha) and dados_user.get("senha") != senha:
                                st.session_state.erro_login_msg = "Uso inválido de ID de sessão ou credenciais incorretas"
                            else:
                                st.session_state.autenticado = True
                                st.session_state.usuario_logado = user_clean
                                st.session_state.erro_login_msg = None
                                st.rerun()

            if st.session_state.get("erro_login_msg"):
                st.markdown(f'''<div class="error-box">{st.session_state.erro_login_msg}</div>''', unsafe_allow_html=True)

    return False