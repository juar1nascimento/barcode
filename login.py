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

# Logo da Prefeitura da Serra em SVG Nativo
LOGO_SERRA_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 180" width="280" height="97"><g><path d="M 15,15 L 145,15 C 145,105 130,150 80,170 C 30,150 15,105 15,15 Z" fill="#1b8e42" stroke="#146830" stroke-width="2"/><path d="M 27,27 L 133,27 C 133,98 120,138 80,155 C 40,138 27,98 27,27 Z" fill="#ffffff"/><path d="M 27,27 L 133,27 L 133,48 L 27,48 Z" fill="#1b8e42"/><text x="80" y="42" font-family="Arial, Helvetica, sans-serif" font-weight="bold" font-size="15" fill="#ffffff" text-anchor="middle">SERRA</text><text x="44" y="40" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#ffffff" text-anchor="middle">1535</text><text x="116" y="40" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#ffffff" text-anchor="middle">1822</text><text x="33" y="40" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">★</text><text x="127" y="40" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">★</text><circle cx="80" cy="72" r="16" fill="none" stroke="#000000" stroke-width="4" stroke-dasharray="6,4"/><circle cx="80" cy="72" r="11" fill="#fbd100" stroke="#000000" stroke-width="1.5"/><path d="M 74,78 L 74,68 L 82,68 L 80,64 L 86,64 L 84,68 L 86,78 Z" fill="#000000"/><rect x="42" y="93" width="76" height="10" fill="#000000"/><rect x="46" y="89" width="8" height="4" fill="#000000"/><rect x="58" y="89" width="8" height="4" fill="#000000"/><rect x="70" y="89" width="8" height="4" fill="#000000"/><rect x="82" y="89" width="8" height="4" fill="#000000"/><rect x="94" y="89" width="8" height="4" fill="#000000"/><rect x="106" y="89" width="8" height="4" fill="#000000"/><path d="M 40,135 L 120,135 C 120,120 40,120 40,135 Z" fill="#fbd100"/><line x1="80" y1="105" x2="80" y2="120" stroke="#fbd100" stroke-width="2"/><line x1="65" y1="108" x2="72" y2="121" stroke="#fbd100" stroke-width="2"/><line x1="95" y1="108" x2="88" y2="121" stroke="#fbd100" stroke-width="2"/><line x1="53" y1="115" x2="65" y2="124" stroke="#fbd100" stroke-width="2"/><line x1="107" y1="115" x2="95" y2="124" stroke="#fbd100" stroke-width="2"/><path d="M 33,138 Q 50,122 65,135 Q 80,118 95,138 Q 110,125 127,138 L 127,143 C 115,152 45,152 33,143 Z" fill="#2d8647" stroke="#1e5c30" stroke-width="1"/><path d="M 36,143 Q 80,158 124,143 C 110,157 50,157 36,143 Z" fill="#1b4d89"/><text x="35" y="102" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text><text x="125" y="102" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text><text x="80" y="152" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text></g><text x="195" y="62" font-family="Arial, Helvetica, sans-serif" font-size="25" font-weight="normal" fill="#000000" letter-spacing="1">PREFEITURA MUNICIPAL DA</text><text x="193" y="135" font-family="Arial Black, Gadget, sans-serif" font-size="76" font-weight="900" fill="#000000" letter-spacing="-1">SERRA</text></svg>"""

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
        
        # Limpa os parâmetros da URL após ler
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
    # Processa ações vindas do e-mail (se houver)
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
            button[kind="tertiary"] {
                float: right !important; font-size: 12px !important; color: #0056b3 !important;
                text-decoration: underline !important; margin-top: -15px !important; margin-bottom: 10px !important;
                padding: 0 !important; height: auto !important; background: transparent !important; border: none !important;
            }
            div[data-baseweb="input"] {
                background-color: #f4f6f8 !important; border: 1px solid #d1d5da !important; border-radius: 4px !important;
            }
            div[data-baseweb="select"] > div {
                background-color: #ffffff !important; border: 1px solid #d1d5da !important; border-radius: 4px !important;
            }
            div[data-baseweb="select"] svg, div[data-baseweb="input"] button svg { transform: scale(0.65) !important; }
            div[data-testid="stForm"] button[kind="secondaryFormSubmit"],
            div[data-testid="stForm"] button[kind="primaryFormSubmit"] {
                background-color: #555555 !important; color: #ffffff !important; border: none !important;
                border-radius: 4px !important; height: 42px !important; font-size: 14px !important;
                font-weight: 600 !important; margin-top: 15px !important;
            }
            div[data-testid="stForm"] button[kind="secondaryFormSubmit"]:hover,
            div[data-testid="stForm"] button[kind="primaryFormSubmit"]:hover {
                background-color: #333333 !important; color: #ffffff !important;
            }
            .error-box {
                background-color: #fdf2f2; border: 1px solid #f8b4b4; border-left: 4px solid #e02424;
                color: #9b1c1c; padding: 12px 16px; border-radius: 4px; font-size: 13px; margin-top: 15px;
            }
        </style>
    """, unsafe_allow_html=True)

    _, col_center, _ = st.columns([1, 1.8, 1])

    with col_center:
        st.markdown(logo_html, unsafe_allow_html=True)

        # -------------------------------------------------------------
        # TELA 1: DIGITAR E-MAIL DE RECUPERAÇÃO
        # -------------------------------------------------------------
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

            # Botão de navegação fora do formulário
            if st.button("← Voltar ao Login", use_container_width=True, key="btn_voltar_solicitar"):
                st.session_state.tela_atual = "login"
                st.rerun()

        # -------------------------------------------------------------
        # TELA 2: DEFINIR NOVO LOGIN (E-MAIL) E CONFIRMAR SENHA (8 DIGITOS)
        # -------------------------------------------------------------
        elif st.session_state.tela_atual == "redefinicao_criar":
            with st.form(key="form_criar_usuario", clear_on_submit=False):
                st.markdown('<div class="login-title">Redefinição de senha</div>', unsafe_allow_html=True)
                
                st.write("**Login de Usuário (Obrigatório ser E-mail)**")
                novo_usuario = st.text_input(
                    "Usuário", 
                    value=st.session_state.get('email_solicitante', ''), 
                    placeholder="usuario@dominio.com", 
                    label_visibility="collapsed", 
                    key="novo_user"
                )

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
                            # Atualiza/Insere o usuário na base interna como NÃO APROVADO
                            db = carregar_usuarios()
                            db[novo_user_clean] = {
                                "senha": hash_senha(nova_senha),
                                "aprovado": False
                            }
                            salvar_usuarios(db)

                            admin_email = st.secrets.get("email", {}).get("admin_email", ADMIN_EMAIL_DEFAULT)
                            app_url = st.secrets.get("email", {}).get("app_url", "http://localhost:8501").rstrip("/")

                            # Codifica os parâmetros com segurança para a URL
                            params_aprovar = urllib.parse.urlencode({"acao": "aprovar", "usuario": novo_user_clean})
                            params_recusar = urllib.parse.urlencode({"acao": "recusar", "usuario": novo_user_clean})

                            link_aprovar = f"{app_url}/?{params_aprovar}"
                            link_recusar = f"{app_url}/?{params_recusar}"

                            # Notificação enviada ao Administrador com os Botões de Ação
                            corpo_admin = f"""
                            <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
                                <h3 style="color: #1b8e42;">Alerta de Novo Usuário / Solicitação de Cadastro</h3>
                                <p>Um novo cadastro/redefinição foi solicitado no sistema:</p>
                                <ul>
                                    <li><b>E-mail/Usuário Solicitado:</b> {novo_user_clean}</li>
                                </ul>
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

            # Botão de navegação fora do formulário
            if st.button("← Cancelar", use_container_width=True, key="btn_cancelar_criar"):
                st.session_state.tela_atual = "login"
                st.rerun()

        # -------------------------------------------------------------
        # TELA PRINCIPAL DE LOGIN
        # -------------------------------------------------------------
        else:
            with st.form(key="glpi_login_form", clear_on_submit=False):
                st.markdown('<div class="login-title">Faça login na sua conta</div>', unsafe_allow_html=True)

                st.write("**Usuário**")
                usuario = st.text_input("Usuário", value="", placeholder="seuemail@serra.es.gov.br", label_visibility="collapsed", key="login_user")

                st.write("**Senha**")
                senha = st.text_input("Senha", value="", type="password", label_visibility="collapsed", key="login_pass")

                st.write("**Origem de login**")
                origem = st.selectbox("Origem de login", ["SERRA.LOCAL", "BANCO DE DADOS INTERNO"], label_visibility="collapsed", key="login_domain")

                submit = st.form_submit_button("Entrar", use_container_width=True)

                if submit:
                    user_clean = usuario.strip().lower()
                    
                    if not user_clean or not senha.strip():
                        st.session_state.erro_login_msg = "Uso inválido de ID de sessão ou credenciais incorretas"
                    else:
                        db = carregar_usuarios()
                        
                        # Regra 1: Valida se o e-mail está cadastrado no sistema
                        if user_clean not in db:
                            st.session_state.erro_login_msg = "Acesso negado: Este e-mail não está cadastrado no sistema"
                        else:
                            dados_user = db[user_clean]
                            
                            # Regra 2: Valida se o e-mail cadastrado já possui autorização
                            if not dados_user.get("aprovado", False):
                                st.session_state.erro_login_msg = "Seu e-mail está cadastrado, porém ainda aguarda AUTORIZAÇÃO do administrador"
                            # Regra 3: Valida a senha (hash ou padrão)
                            elif dados_user.get("senha") != hash_senha(senha) and dados_user.get("senha") != senha:
                                st.session_state.erro_login_msg = "Uso inválido de ID de sessão ou credenciais incorretas"
                            else:
                                st.session_state.autenticado = True
                                st.session_state.usuario_logado = user_clean
                                st.session_state.erro_login_msg = None
                                st.rerun()

            # Botão de navegação fora do st.form para evitar conflitos de submissão
            if st.button("Esqueceu sua senha?", type="tertiary", key="btn_esqueceu_senha_login"):
                st.session_state.tela_atual = "redefinicao_solicitar"
                st.rerun()

            # Exibição das mensagens de erro
            if st.session_state.get("erro_login_msg"):
                st.markdown(f"""
                    <div class="error-box">
                        {st.session_state.erro_login_msg}
                    </div>
                """, unsafe_allow_html=True)

    return False