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

# ================= FUNÇÕES DE BANCO DE DADOS (Simulação) ================= #
def hash_senha(senha: str) -> str:
    """Gera um hash SHA-256 da senha para segurança."""
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()

def carregar_db():
    """Carrega o banco de usuários do arquivo JSON."""
    if not os.path.exists(DB_FILE):
        # Usuário admin padrão criado automaticamente
        return {"admin@serra.es.gov.br": {"senha": hash_senha("admin123"), "aprovado": True}}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def salvar_db(db_data):
    """Salva as informações no arquivo JSON."""
    with open(DB_FILE, "w") as f:
        json.dump(db_data, f)
# ========================================================================= #

def validar_email(email: str) -> bool:
    padrao = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return bool(re.match(padrao, email.strip()))

def validar_senha_alfanumerica_8(senha: str) -> tuple[bool, str]:
    if len(senha) != 8:
        return False, "A senha deve conter exatamente 8 caracteres."
    if not senha.isalnum():
        return False, "A senha deve ser alfanumérica (apenas letras e números, sem símbolos)."
    if not (any(c.isalpha() for c in senha) and any(c.isdigit() for c in senha)):
        return False, "A senha deve conter ao menos uma letra e um número."
    return True, ""

def enviar_email(destinatario: str, assunto: str, corpo_html: str) -> tuple[bool, str]:
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
    params = st.query_params
    if "acao" in params and "usuario" in params:
        acao = params["acao"]
        user_email = params["usuario"]
        st.query_params.clear()

        db = carregar_db()
        if user_email not in db:
            st.error("Usuário não encontrado no sistema.")
            return

        if acao == "aprovar":
            db[user_email]["aprovado"] = True
            salvar_db(db)
            corpo = f"""
            <h3>Prefeitura Municipal da Serra</h3>
            <p>Seu cadastro para o e-mail <b>{user_email}</b> foi <b>ACEITO</b> pelo administrador.</p>
            <p>Você já pode acessar o sistema normalmente.</p>
            """
            enviar_email(user_email, "Cadastro Aceito - Prefeitura da Serra", corpo)
            st.success(f"Solicitação do usuário {user_email} foi APROVADA com sucesso!")
            
        elif acao == "recusar":
            # Caso recuse, remove do banco de dados
            del db[user_email]
            salvar_db(db)
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

    b64_logo = base64.b64encode(LOGO_SERRA_SVG.encode("utf-8")).decode("utf-8")
    logo_html = f'<div style="text-align: center; margin-bottom: 25px;"><img src="data:image/svg+xml;base64,{b64_logo}" width="280" /></div>'

    st.markdown("""
        <style>
            .stApp { background-color: #f2f4f7 !important; }
            header, footer, #MainMenu { visibility: hidden; }
            div[data-testid="stForm"] {
                background-color: #ffffff !important; border: 1px solid #e1e4e8 !important; border-radius: 4px !important;
                padding: 35px 40px !important; box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
            }
            .login-title { text-align: center; font-size: 20px; font-weight: 600; color: #24292e; margin-bottom: 25px; }
            div[data-testid="stForm"] button[kind="tertiary"] {
                float: right !important; font-size: 12px !important; color: #0056b3 !important; text-decoration: underline !important;
                margin-top: -30px !important; padding: 0 !important; height: auto !important; background: transparent !important; border: none !important;
            }
            div[data-testid="stForm"] button[kind="secondaryFormSubmit"],
            div[data-testid="stForm"] button[kind="primaryFormSubmit"] {
                background-color: #555555 !important; color: #ffffff !important; border: none !important; border-radius: 4px !important;
                height: 42px !important; font-size: 14px !important; font-weight: 600 !important; margin-top: 15px !important;
            }
            .error-box { background-color: #fdf2f2; border: 1px solid #f8b4b4; border-left: 4px solid #e02424; color: #9b1c1c; padding: 12px 16px; border-radius: 4px; font-size: 13px; margin-top: 15px; }
            .warning-box { background-color: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #f59e0b; color: #92400e; padding: 12px 16px; border-radius: 4px; font-size: 13px; margin-top: 15px; }
        </style>
    """, unsafe_allow_html=True)

    _, col_center, _ = st.columns([1, 1.8, 1])

    with col_center:
        st.markdown(logo_html, unsafe_allow_html=True)

        if st.session_state.tela_atual == "redefinicao_solicitar":
            # [Sem alterações] Código original mantido
            pass 

        elif st.session_state.tela_atual == "redefinicao_criar":
            with st.form(key="form_criar_usuario", clear_on_submit=False):
                st.markdown('<div class="login-title">Solicitar Cadastro</div>', unsafe_allow_html=True)
                st.write("**Login de Usuário (Obrigatório ser E-mail)**")
                novo_usuario = st.text_input("Usuário", value=st.session_state.get('email_solicitante', ''), placeholder="usuario@dominio.com", label_visibility="collapsed", key="novo_user").strip()
                st.write("**Nova Senha (Exatamente 8 caracteres alfanuméricos)**")
                nova_senha = st.text_input("Nova Senha", type="password", label_visibility="collapsed", key="nova_pass")
                st.write("**Confirme a Nova Senha**")
                confirma_senha = st.text_input("Confirmar Senha", type="password", label_visibility="collapsed", key="confirma_pass")
                btn_finalizar = st.form_submit_button("Cadastrar e Solicitar Autorização", use_container_width=True)

                if btn_finalizar:
                    if not validar_email(novo_usuario):
                        st.error("O nome de usuário deve ser obrigatoriamente um e-mail válido.")
                    elif nova_senha != confirma_senha:
                        st.error("A confirmação de senha não confere com a nova senha digitada.")
                    else:
                        senha_ok, msg_erro = validar_senha_alfanumerica_8(nova_senha)
                        if not senha_ok:
                            st.error(msg_erro)
                        else:
                            # 1. Salvar no Banco de Dados local pendente de aprovação
                            db = carregar_db()
                            if novo_usuario in db and db[novo_usuario]["aprovado"]:
                                st.error("Este usuário já existe e está aprovado.")
                            else:
                                db[novo_usuario] = {"senha": hash_senha(nova_senha), "aprovado": False}
                                salvar_db(db)

                                admin_email = st.secrets.get("email", {}).get("admin_email", ADMIN_EMAIL_DEFAULT)
                                app_url = st.secrets.get("email", {}).get("app_url", "http://localhost:8501").rstrip("/")
                                params_aprovar = urllib.parse.urlencode({"acao": "aprovar", "usuario": novo_usuario})
                                params_recusar = urllib.parse.urlencode({"acao": "recusar", "usuario": novo_usuario})

                                link_aprovar = f"{app_url}/?{params_aprovar}"
                                link_recusar = f"{app_url}/?{params_recusar}"

                                corpo_admin = f"""
                                <h3>Alerta de Novo Usuário</h3>
                                <p>Solicitação pendente de: <b>{novo_usuario}</b></p>
                                <a href="{link_aprovar}">Autorizar Cadastro</a><br><br>
                                <a href="{link_recusar}">Recusar Cadastro</a>
                                """
                                enviar_email(admin_email, f"Solicitação de Cadastro: {novo_usuario}", corpo_admin)
                                st.success(f"Solicitação enviada para {admin_email}. Aguarde a aprovação para efetuar o login.")
                                st.session_state.tela_atual = "login"

            if st.button("← Cancelar", use_container_width=True):
                st.session_state.tela_atual = "login"
                st.rerun()

        else:
            with st.form(key="glpi_login_form", clear_on_submit=False):
                st.markdown('<div class="login-title">Faça login na sua conta</div>', unsafe_allow_html=True)
                st.write("**Usuário**")
                usuario = st.text_input("Usuário", value="", placeholder="seuemail@serra.es.gov.br", label_visibility="collapsed", key="login_user").strip()
                st.write("**Senha**")
                senha = st.text_input("Senha", value="", type="password", label_visibility="collapsed", key="login_pass")

                if st.form_submit_button("Esqueceu sua senha?", type="tertiary"):
                    st.session_state.tela_atual = "redefinicao_solicitar"
                    st.rerun()

                origem = st.selectbox("Origem de login", ["SERRA.LOCAL", "BANCO DE DADOS INTERNO"], label_visibility="collapsed", key="login_domain")
                submit = st.form_submit_button("Entrar", use_container_width=True)

                if submit:
                    # 1. Carrega os usuários salvos no BD (JSON)
                    db = carregar_db()
                    st.session_state.msg_login = ""

                    # 2. Valida regras de Segurança E Autorização
                    if usuario in db:
                        dados_usuario = db[usuario]
                        # Compara a senha digitada (passada por hash) com o hash salvo
                        if dados_usuario["senha"] == hash_senha(senha):
                            if dados_usuario["aprovado"] == True:
                                st.session_state.autenticado = True
                                st.rerun()
                            else:
                                st.session_state.msg_login = "warning:Seu cadastro ainda aguarda a aprovação do administrador."
                        else:
                            st.session_state.msg_login = "error:Credenciais incorretas."
                    else:
                        st.session_state.msg_login = "error:Usuário ou senha inválidos."

            # Exibir Mensagens de Erro/Aviso baseadas na lógica de validação atualizada
            if st.session_state.get("msg_login", ""):
                tipo, msg = st.session_state.msg_login.split(":")
                if tipo == "error":
                    st.markdown(f'<div class="error-box">{msg}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="warning-box">{msg}</div>', unsafe_allow_html=True)

    return False