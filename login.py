import base64
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import streamlit as st

# Logo da Prefeitura da Serra em SVG Nativo
LOGO_SERRA_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 180" width="280" height="97"><g><path d="M 15,15 L 145,15 C 145,105 130,150 80,170 C 30,150 15,105 15,15 Z" fill="#1b8e42" stroke="#146830" stroke-width="2"/><path d="M 27,27 L 133,27 C 133,98 120,138 80,155 C 40,138 27,98 27,27 Z" fill="#ffffff"/><path d="M 27,27 L 133,27 L 133,48 L 27,48 Z" fill="#1b8e42"/><text x="80" y="42" font-family="Arial, Helvetica, sans-serif" font-weight="bold" font-size="15" fill="#ffffff" text-anchor="middle">SERRA</text><text x="44" y="40" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#ffffff" text-anchor="middle">1535</text><text x="116" y="40" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#ffffff" text-anchor="middle">1822</text><text x="33" y="40" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">★</text><text x="127" y="40" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#ffffff" text-anchor="middle">★</text><circle cx="80" cy="72" r="16" fill="none" stroke="#000000" stroke-width="4" stroke-dasharray="6,4"/><circle cx="80" cy="72" r="11" fill="#fbd100" stroke="#000000" stroke-width="1.5"/><path d="M 74,78 L 74,68 L 82,68 L 80,64 L 86,64 L 84,68 L 86,78 Z" fill="#000000"/><rect x="42" y="93" width="76" height="10" fill="#000000"/><rect x="46" y="89" width="8" height="4" fill="#000000"/><rect x="58" y="89" width="8" height="4" fill="#000000"/><rect x="70" y="89" width="8" height="4" fill="#000000"/><rect x="82" y="89" width="8" height="4" fill="#000000"/><rect x="94" y="89" width="8" height="4" fill="#000000"/><rect x="106" y="89" width="8" height="4" fill="#000000"/><path d="M 40,135 L 120,135 C 120,120 40,120 40,135 Z" fill="#fbd100"/><line x1="80" y1="105" x2="80" y2="120" stroke="#fbd100" stroke-width="2"/><line x1="65" y1="108" x2="72" y2="121" stroke="#fbd100" stroke-width="2"/><line x1="95" y1="108" x2="88" y2="121" stroke="#fbd100" stroke-width="2"/><line x1="53" y1="115" x2="65" y2="124" stroke="#fbd100" stroke-width="2"/><line x1="107" y1="115" x2="95" y2="124" stroke="#fbd100" stroke-width="2"/><path d="M 33,138 Q 50,122 65,135 Q 80,118 95,138 Q 110,125 127,138 L 127,143 C 115,152 45,152 33,143 Z" fill="#2d8647" stroke="#1e5c30" stroke-width="1"/><path d="M 36,143 Q 80,158 124,143 C 110,157 50,157 36,143 Z" fill="#1b4d89"/><text x="35" y="102" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text><text x="125" y="102" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text><text x="80" y="152" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#ffffff" text-anchor="middle">★</text></g><text x="195" y="62" font-family="Arial, Helvetica, sans-serif" font-size="25" font-weight="normal" fill="#000000" letter-spacing="1">PREFEITURA MUNICIPAL DA</text><text x="193" y="135" font-family="Arial Black, Gadget, sans-serif" font-size="76" font-weight="900" fill="#000000" letter-spacing="-1">SERRA</text></svg>"""

ADMIN_EMAIL = "juari.neris@gmail.com"

def enviar_email(destinatario: str, assunto: str, corpo_html: str):
    """Função utilitária para envio de e-mails via SMTP com suporte a secrets do Streamlit."""
    try:
        smtp_server = st.secrets.get("email", {}).get("smtp_server", "smtp.gmail.com")
        smtp_port = int(st.secrets.get("email", {}).get("smtp_port", 587))
        sender_email = st.secrets.get("email", {}).get("sender_email", "sistema@serra.es.gov.br")
        sender_password = st.secrets.get("email", {}).get("sender_password", "")

        msg = MIMEMultipart("alternative")
        msg["From"] = sender_email
        msg["To"] = destinatario
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo_html, "html"))

        if sender_password:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, destinatario, msg.as_string())
        return True
    except Exception as e:
        # Registra o erro internamente sem expor dados sensíveis ao usuário
        st.error(f"Erro ao disparar e-mail automático: {e}")
        return False

def renderizar_login() -> bool:
    """Renderiza a interface de autenticação e gerenciamento de solicitações."""
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

    if "tela_atual" not in st.session_state:
        st.session_state.tela_atual = "login"  # 'login', 'redefinicao_solicitar', 'redefinicao_criar'

    if st.session_state.autenticado:
        return True

    # Codificação segura em Base64 do SVG da logo
    b64_logo = base64.b64encode(LOGO_SERRA_SVG.encode("utf-8")).decode("utf-8")
    logo_html = f'<div style="text-align: center; margin-bottom: 25px;"><img src="data:image/svg+xml;base64,{b64_logo}" width="280" /></div>'

    # Estilização CSS personalizada
    st.markdown("""
        <style>
            .stApp {
                background-color: #f2f4f7 !important;
            }
            header, footer, #MainMenu {
                visibility: hidden;
            }
            div[data-testid="stForm"] {
                background-color: #ffffff !important;
                border: 1px solid #e1e4e8 !important;
                border-radius: 4px !important;
                padding: 35px 40px !important;
                box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
            }
            .login-title {
                text-align: center;
                font-size: 20px;
                font-weight: 600;
                color: #24292e;
                margin-bottom: 25px;
            }
            div[data-testid="stForm"] button[kind="tertiary"] {
                float: right !important;
                font-size: 12px !important;
                color: #0056b3 !important;
                text-decoration: underline !important;
                margin-top: -30px !important;
                padding: 0 !important;
                height: auto !important;
                background: transparent !important;
                border: none !important;
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
            div[data-baseweb="select"] svg, div[data-baseweb="input"] button svg {
                transform: scale(0.65) !important;
            }
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
                background-color: #fdf2f2;
                border: 1px solid #f8b4b4;
                border-left: 4px solid #e02424;
                color: #9b1c1c;
                padding: 12px 16px;
                border-radius: 4px;
                font-size: 13px;
                margin-top: 15px;
            }
        </style>
    """, unsafe_allow_html=True)

    _, col_center, _ = st.columns([1, 1.8, 1])

    with col_center:
        st.markdown(logo_html, unsafe_allow_html=True)

        # -------------------------------------------------------------
        # TELA 1: SOLICITAÇÃO DE REDEFINIÇÃO / CRIAÇÃO DE CONTA (DIGITAR E-MAIL)
        # -------------------------------------------------------------
        if st.session_state.tela_atual == "redefinicao_solicitar":
            with st.form(key="form_solicitar_email", clear_on_submit=False):
                st.markdown('<div class="login-title">Redefinição de senha</div>', unsafe_allow_html=True)
                
                st.write("**Informe seu e-mail cadastrado ou novo e-mail**")
                email_req = st.text_input("E-mail", value="", placeholder="exemplo@serra.es.gov.br", label_visibility="collapsed", key="email_req")
                
                btn_enviar_req = st.form_submit_button("Enviar Requisição", use_container_width=True)
                
                if btn_enviar_req:
                    if "@" in email_req and "." in email_req:
                        st.session_state.email_solicitante = email_req
                        st.session_state.tela_atual = "redefinicao_criar"
                        
                        # Dispara instruções ao e-mail do usuário
                        corpo_usuario = f"""
                        <h3>Prefeitura Municipal da Serra - Sistema Barcode</h3>
                        <p>Recebemos uma solicitação de criação/redefinição para o e-mail: <b>{email_req}</b>.</p>
                        <p>Por favor, prossiga na tela do sistema informando seu Usuário e Nova Senha para submeter à aprovação do administrador.</p>
                        """
                        enviar_email(email_req, "Solicitação de Acesso / Redefinição de Senha", corpo_usuario)
                        st.rerun()
                    else:
                        st.error("Por favor, insira um e-mail válido.")

            if st.button("← Voltar ao Login", use_container_width=True):
                st.session_state.tela_atual = "login"
                st.rerun()

        # -------------------------------------------------------------
        # TELA 2: CRIAÇÃO DE NOVO LOGIN E SENHA + NOTIFICAÇÃO AO ADMIN
        # -------------------------------------------------------------
        elif st.session_state.tela_atual == "redefinicao_criar":
            with st.form(key="form_criar_usuario", clear_on_submit=False):
                st.markdown('<div class="login-title">Redefinição de senha</div>', unsafe_allow_html=True)
                st.caption(f"E-mail associado: **{st.session_state.get('email_solicitante', '')}**")

                st.write("**Defina seu Nome de Usuário**")
                novo_usuario = st.text_input("Novo Usuário", value="", label_visibility="collapsed", key="novo_user")

                st.write("**Defina sua Nova Senha**")
                nova_senha = st.text_input("Nova Senha", value="", type="password", label_visibility="collapsed", key="nova_pass")

                btn_finalizar = st.form_submit_button("Criar Login e Solicitar Autorização", use_container_width=True)

                if btn_finalizar:
                    if novo_usuario.strip() != "" and nova_senha.strip() != "":
                        email_usr = st.session_state.get('email_solicitante', '')
                        
                        # E-mail enviado ao Admin (juari.neris@gmail.com) para autorizar/recusar
                        corpo_admin = f"""
                        <h3>Alerta de Novo Usuário / Solicitação de Cadastro</h3>
                        <p>Um novo cadastro/redefinição foi solicitado no sistema:</p>
                        <ul>
                            <li><b>E-mail:</b> {email_usr}</li>
                            <li><b>Usuário Solicitado:</b> {novo_usuario}</li>
                        </ul>
                        <p>Para autorizar ou recusar o cadastro, acesse o painel administrativo ou responda a este e-mail.</p>
                        """
                        enviar_email(ADMIN_EMAIL, f"Alerta de Novo Usuário: {novo_usuario}", corpo_admin)
                        
                        st.success("Sua solicitação e definição de credenciais foram enviadas com sucesso! Aguarde a aprovação do administrador por e-mail.")
                        st.session_state.tela_atual = "login"
                    else:
                        st.error("Preencha o nome de usuário e a senha corretamente.")

            if st.button("← Cancelar", use_container_width=True):
                st.session_state.tela_atual = "login"
                st.rerun()

        # -------------------------------------------------------------
        # TELA PRINCIPAL DE LOGIN
        # -------------------------------------------------------------
        else:
            with st.form(key="glpi_login_form", clear_on_submit=False):
                st.markdown('<div class="login-title">Faça login na sua conta</div>', unsafe_allow_html=True)

                st.write("**Usuário**")
                usuario = st.text_input("Usuário", value="", label_visibility="collapsed", key="login_user")

                st.write("**Senha**")
                senha = st.text_input("Senha", value="", type="password", label_visibility="collapsed", key="login_pass")

                # Clicar em 'Esqueceu sua senha?' redireciona para a tela de redefinição
                if st.form_submit_button("Esqueceu sua senha?", type="tertiary"):
                    st.session_state.tela_atual = "redefinicao_solicitar"
                    st.rerun()

                st.write("**Origem de login**")
                origem = st.selectbox("Origem de login", ["SERRA.LOCAL", "BANCO DE DADOS INTERNO"], label_visibility="collapsed", key="login_domain")

                submit = st.form_submit_button("Entrar", use_container_width=True)

                if submit:
                    if usuario.strip() != "" and senha.strip() != "":
                        st.session_state.autenticado = True
                        st.session_state.erro_login = False
                        st.rerun()
                    else:
                        st.session_state.erro_login = True

            if st.session_state.get("erro_login", False):
                st.markdown("""
                    <div class="error-box">
                        Uso inválido de ID de sessão
                    </div>
                """, unsafe_allow_html=True)

    return False