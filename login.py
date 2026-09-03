import base64
import re
import smtplib
import urllib.parse
import json
import os
import hashlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import streamlit as st

# Logo da Prefeitura da Serra em SVG Nativo
LOGO_SERRA_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 180" width="280" height="97"><g><path d="M 15,15 L 145,15 C 145,105 130,150 80,170 C 30,150 15,105 15,15 Z" fill="#1b8e42" stroke="#146830" stroke-width="2"/><path d="M 27,27 L 133,27 C 133,98 120,138 80,155 C 40,138 27,98 27,27 Z" fill="#ffffff"/><path d="M 27,27 L 133,27 L 133,48 L 27,48 Z" fill="#1b8e42"/><text x="80" y="42" font-family="Arial, Helvetica, sans-serif" font-weight="bold" font-size="15" fill="#ffffff" text-anchor="middle">SERRA</text><text x="44" y="40" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#ffffff" text-anchor="middle">1535</text><text x="116" y="40" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#ffffff" text-anchor="middle">1822</text><text x="33" y="40" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">★</text><text x="127" y="40" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">★</text><circle cx="80" cy="72" r="16" fill="none" stroke="#000000" stroke-width="4" stroke-dasharray="6,4"/><circle cx="80" cy="72" r="11" fill="#fbd100" stroke="#000000" stroke-width="1.5"/><path d="M 74,78 L 74,68 L 82,68 L 80,64 L 86,64 L 84,68 L 86,78 Z" fill="#000000"/><rect x="42" y="93" width="76" height="10" fill="#000000"/><rect x="46" y="89" width="8" height="4" fill="#000000"/><rect x="58" y="89" width="8" height="4" fill="#000000"/><rect x="70" y="89" width="8" height="4" fill="#000000"/><rect x="82" y="89" width="8" height="4" fill="#000000"/><rect x="94" y="89" width="8" height="4" fill="#000000"/><rect x="106" y="89" width="8" height="4" fill="#000000"/><path d="M 40,135 L 120,135 C 120,120 40,120 40,135 Z" fill="#fbd100"/><line x1="80" y1="105" x2="80" y2="120" stroke="#fbd100" stroke-width="2"/><line x1="65" y1="108" x2="72" y2="121" stroke="#fbd100" stroke-width="2"/><line x1="95" y1="108" x2="88" y2="121" stroke="#fbd100" stroke-width="2"/><line x1="53" y1="115" x2="65" y2="124" stroke="#fbd100" stroke-width="2"/><line x1="107" y1="115" x2="95" y2="124" stroke="#fbd100" stroke-width="2"/><path d="M 33,138 Q 50,122 65,135 Q 80,118 95,138 Q 110,125 127,138 L 127,143 C 115,152 45,152 33,143 Z" fill="#2d8647" stroke="#1e5c30" stroke-width="1"/><path d="M 36,143 Q 80,158 124,143 C 110,157 50,157 36,143 Z" fill="#1b4d89"/><text x="35" y="102" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text><text x="125" y="102" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text><text x="80" y="152" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text></g><text x="195" y="62" font-family="Arial, Helvetica, sans-serif" font-size="25" font-weight="normal" fill="#000000" letter-spacing="1">PREFEITURA MUNICIPAL DA</text><text x="193" y="135" font-family="Arial Black, Gadget, sans-serif" font-size="76" font-weight="900" fill="#000000" letter-spacing="-1">SERRA</text></svg>"""

ADMIN_EMAIL_DEFAULT = "juari.neris@gmail.com"
DB_FILE = "db_usuarios.json"

# ================= FUNÇÕES DE BANCO DE DADOS E HASH ================= #
def hash_senha(senha: str) -> str:
    """Gera um hash SHA-256 da senha para armazenamento seguro."""
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()

def carregar_db() -> dict:
    """Carrega a base de dados de usuários do arquivo JSON."""
    if not os.path.exists(DB_FILE):
        # Usuário administrador padrão (já autorizado por padrão)
        db_inicial = {
            "admin@serra.es.gov.br": {
                "senha": hash_senha("admin123"),
                "aprovado": True
            }
        }
        salvar_db(db_inicial)
        return db_inicial
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def salvar_db(db_data: dict):
    """Salva os dados atualizados no arquivo JSON."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db_data, f, indent=4, ensure_ascii=False)

# ================= VALIDAÇÕES E E-MAIL ================= #
def validar_email(email: str) -> bool:
    """Valida formato de e-mail."""
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

# ================= PROCESSAMENTO DE REQUISIÇÕES VIA URL ================= #
def processar_acao_via_url():
    """Captura e processa a aprovação/recusa do administrador enviada por e-mail."""
    params = st.query_params
    if "acao" in params and "usuario" in params:
        acao = params["acao"]
        user_email = params["usuario"].strip().lower()
        
        st.query_params.clear()
        db = carregar_db()

        if user_email in db:
            if acao == "aprovar":
                db[user_email]["aprovado"] = True
                salvar_db(db)
                corpo = f"""
                <h3>Prefeitura Municipal da Serra</h3>
                <p>Seu acesso para o e-mail <b>{user_email}</b> foi <b>APROVADO E AUTORIZADO</b> pelo administrador.</p>
                <p>Você já pode acessar o sistema normalmente.</p>
                """
                enviar_email(user_email, "Acesso Autorizado - Prefeitura da Serra", corpo)
                st.success(f"O acesso do usuário '{user_email}' foi APROVADO e AUTORIZADO com sucesso!")
            elif acao == "recusar":
                db[user_email]["aprovado"] = False
                salvar_db(db)
                corpo = f"""
                <h3>Prefeitura Municipal da Serra</h3>
                <p>Sua solicitação de acesso para o e-mail <b>{user_email}</b> foi <b>RECUSADA</b> pelo administrador.</p>
                """
                enviar_email(user_email, "Acesso Recusado - Prefeitura da Serra", corpo)
                st.error(f"A solicitação do usuário '{user_email}' foi RECUSADA.")
        else:
            st.error("Usuário informado no link não consta no banco de dados.")

# ================= RENDERIZAÇÃO DA INTERFACE DE LOGIN ================= #
def renderizar_login() -> bool:
    processar_acao_via_url()

    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

    if "tela_atual" not in st.session_state:
        st.session_state.tela_atual = "login"

    if st.session_state.autenticado:
        return True

    b64_logo = base64.b64encode(LOGO_SERRA_SVG.encode("utf-8")).decode("utf-8")
    logo_html = f'<div style="text-align: center; margin-bottom: 25px;"><img src="data:image/svg+xml;base64,{b64_logo}" width="280" /></div>'

    st.markdown("""
        <style>
            .stApp { background-color: #f2f4f7 !important; }
            header, footer, #MainMenu { visibility: hidden; }
            div[data-testid="stForm"] {
                background-color: #ffffff !important;
                border: 1px solid #e1e4e8 !important;
                border-radius: 4px !important;
                padding: 35px 40px !important;
                box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
            }
            .login-title {
                text-align: center; font-size: 20px; font-weight: 600; color: #24292e; margin-bottom: 25px;
            }
            .error-box {
                background-color: #fdf2f2; border: 1px solid #f8b4b4; border-left: 4px solid #e02424;
                color: #9b1c1c; padding: 12px 16px; border-radius: 4px; font-size: 13px; margin-top: 15px;
            }
            .warning-box {
                background-color: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #f59e0b;
                color: #92400e; padding: 12px 16px; border-radius: 4px; font-size: 13px; margin-top: 15px;
            }
        </style>
    """, unsafe_allow_html=True)

    _, col_center, _ = st.columns([1, 1.8, 1])

    with col_center:
        st.markdown(logo_html, unsafe_allow_html=True)

        # -------------------------------------------------------------
        # TELA 1: RECUPERAÇÃO DE SENHA
        # -------------------------------------------------------------
        if st.session_state.tela_atual == "redefinicao_solicitar":
            with st.form(key="form_solicitar_recuperacao", clear_on_submit=False):
                st.markdown('<div class="login-title">Esqueceu sua senha?</div>', unsafe_allow_html=True)
                st.write("Informe seu e-mail cadastrado para solicitar a redefinição de acesso.")
                
                email_req = st.text_input("E-mail de Cadastro", placeholder="seuemail@serra.es.gov.br", key="email_recup").strip().lower()
                btn_enviar_recup = st.form_submit_button("Solicitar Redefinição", use_container_width=True)

                if btn_enviar_recup:
                    if not validar_email(email_req):
                        st.error("Informe um e-mail válido.")
                    else:
                        db = carregar_db()
                        if email_req not in db:
                            st.error("Acesso negado: Este e-mail não está cadastrado no sistema.")
                        elif not db[email_req].get("aprovado", False):
                            st.warning("Seu e-mail está cadastrado, mas ainda aguarda autorização do administrador.")
                        else:
                            admin_email = st.secrets.get("email", {}).get("admin_email", ADMIN_EMAIL_DEFAULT)
                            corpo_admin = f"""
                            <h3>Solicitação de Redefinição de Senha</h3>
                            <p>O usuário <b>{email_req}</b> (Autorizado) solicitou a redefinição de sua senha.</p>
                            """
                            enviar_email(admin_email, f"Redefinição de Senha Solicitada: {email_req}", corpo_admin)
                            st.success(f"Solicitação enviada ao administrador ({admin_email}). Em breve você receberá instruções.")

            if st.button("← Voltar para a Tela de Login", use_container_width=True, key="btn_voltar_recup"):
                st.session_state.tela_atual = "login"
                st.rerun()

        # -------------------------------------------------------------
        # TELA 2: SOLICITAR NOVO CADASTRO / NOVO USUÁRIO
        # -------------------------------------------------------------
        elif st.session_state.tela_atual == "redefinicao_criar":
            with st.form(key="form_criar_usuario", clear_on_submit=False):
                st.markdown('<div class="login-title">Solicitar Cadastro de Novo Usuário</div>', unsafe_allow_html=True)
                
                st.write("**E-mail do Usuário (Obrigatório ser um e-mail válido)**")
                novo_usuario = st.text_input(
                    "Usuário", 
                    placeholder="usuario@serra.es.gov.br", 
                    label_visibility="collapsed", 
                    key="novo_user"
                ).strip().lower()

                st.write("**Senha (Exatamente 8 caracteres alfanuméricos)**")
                nova_senha = st.text_input("Nova Senha", type="password", placeholder="Ex: serra123", label_visibility="collapsed", key="nova_pass")

                st.write("**Confirme a Senha**")
                confirma_senha = st.text_input("Confirmar Senha", type="password", placeholder="Repita a senha", label_visibility="collapsed", key="confirma_pass")

                btn_cadastrar = st.form_submit_button("Cadastrar e Solicitar Autorização", use_container_width=True)

                if btn_cadastrar:
                    if not validar_email(novo_usuario):
                        st.error("O nome de usuário deve ser um e-mail válido.")
                    elif nova_senha != confirma_senha:
                        st.error("A confirmação de senha não confere com a senha digitada.")
                    else:
                        senha_ok, msg_erro = validar_senha_alfanumerica_8(nova_senha)
                        if not senha_ok:
                            st.error(msg_erro)
                        else:
                            db = carregar_db()
                            if novo_usuario in db and db[novo_usuario].get("aprovado", False):
                                st.error("Este e-mail já está cadastrado e devidamente autorizado no sistema.")
                            else:
                                db[novo_usuario] = {
                                    "senha": hash_senha(nova_senha),
                                    "aprovado": False
                                }
                                salvar_db(db)

                                admin_email = st.secrets.get("email", {}).get("admin_email", ADMIN_EMAIL_DEFAULT)
                                app_url = st.secrets.get("email", {}).get("app_url", "http://localhost:8501").rstrip("/")

                                params_aprovar = urllib.parse.urlencode({"acao": "aprovar", "usuario": novo_usuario})
                                params_recusar = urllib.parse.urlencode({"acao": "recusar", "usuario": novo_usuario})

                                link_aprovar = f"{app_url}/?{params_aprovar}"
                                link_recusar = f"{app_url}/?{params_recusar}"

                                corpo_admin = f"""
                                <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
                                    <h3 style="color: #1b8e42;">Solicitação de Autorização de Acesso</h3>
                                    <p>Um novo usuário solicitou cadastro para acessar o sistema:</p>
                                    <ul>
                                        <li><b>E-mail:</b> {novo_usuario}</li>
                                    </ul>
                                    <p>Clique em uma das opções abaixo para autorizar ou recusar o acesso:</p>
                                    <div style="margin-top: 20px;">
                                        <a href="{link_aprovar}" style="background-color: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; margin-right: 10px;">Autorizar Acesso</a>
                                        <a href="{link_recusar}" style="background-color: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">Recusar Acesso</a>
                                    </div>
                                </div>
                                """
                                enviar_email(admin_email, f"Solicitação de Acesso: {novo_usuario}", corpo_admin)
                                st.success(f"Solicitação enviada com sucesso! Um e-mail de autorização foi encaminhado para o administrador ({admin_email}). Aguarde a liberação para efetuar login.")

            if st.button("← Voltar para a Tela de Login", use_container_width=True, key="btn_voltar_cadastro"):
                st.session_state.tela_atual = "login"
                st.rerun()

        # -------------------------------------------------------------
        # TELA PRINCIPAL DE LOGIN COM REGRA DE AUTORIZAÇÃO
        # -------------------------------------------------------------
        else:
            with st.form(key="glpi_login_form", clear_on_submit=False):
                st.markdown('<div class="login-title">Faça login na sua conta</div>', unsafe_allow_html=True)

                st.write("**Usuário (E-mail)**")
                usuario = st.text_input("Usuário", value="", placeholder="seuemail@serra.es.gov.br", label_visibility="collapsed", key="login_user").strip().lower()

                st.write("**Senha**")
                senha = st.text_input("Senha", value="", type="password", label_visibility="collapsed", key="login_pass")

                st.write("**Origem de login**")
                origem = st.selectbox("Origem de login", ["SERRA.LOCAL", "BANCO DE DADOS INTERNO"], label_visibility="collapsed", key="login_domain")

                submit = st.form_submit_button("Entrar", use_container_width=True)

                if submit:
                    st.session_state.msg_login = ""

                    if not usuario or not senha:
                        st.session_state.msg_login = "error:Por favor, preencha o usuário (e-mail) e a senha."
                    elif not validar_email(usuario):
                        st.session_state.msg_login = "error:O usuário informado deve possuir formato de e-mail válido."
                    else:
                        db = carregar_db()
                        
                        # REGRA DE ACESSO EXCLUSIVO: E-MAIL CADASTRADO E AUTORIZADO
                        if usuario not in db:
                            st.session_state.msg_login = "error:Acesso negado: Este e-mail não está cadastrado no sistema."
                        else:
                            dados = db[usuario]
                            if dados["senha"] != hash_senha(senha):
                                st.session_state.msg_login = "error:Senha incorreta."
                            elif not dados.get("aprovado", False):
                                st.session_state.msg_login = "warning:Seu e-mail está cadastrado, porém ainda aguarda AUTORIZAÇÃO do administrador."
                            else:
                                # Sucesso: E-mail cadastrado e autorizado + Senha correta
                                st.session_state.autenticado = True
                                st.session_state.usuario_logado = usuario
                                st.rerun()

            # Botões auxiliares fora do formulário para navegação direta e limpa
            col_esq, col_dir = st.columns(2)
            with col_esq:
                if st.button("Esqueceu sua senha?", use_container_width=True, key="btn_nav_esqueceu"):
                    st.session_state.tela_atual = "redefinicao_solicitar"
                    st.rerun()
            with col_dir:
                if st.button("Solicitar Novo Cadastro", use_container_width=True, key="btn_nav_cadastro"):
                    st.session_state.tela_atual = "redefinicao_criar"
                    st.rerun()

            # Mensagens de alerta/erro
            if st.session_state.get("msg_login", ""):
                tipo, msg = st.session_state.msg_login.split(":", 1)
                if tipo == "error":
                    st.markdown(f'<div class="error-box">{msg}</div>', unsafe_allow_html=True)
                elif tipo == "warning":
                    st.markdown(f'<div class="warning-box">{msg}</div>', unsafe_allow_html=True)

    return False