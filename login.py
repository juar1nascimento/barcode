import streamlit as st
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==========================================
# CONFIGURAÇÕES DE AUTENTICAÇÃO E EMAIL
# ==========================================
URL_LOGO_GITHUB = "https://raw.githubusercontent.com/juar1nascimento/barcode/main/image_6ca286.png"
EMAIL_ADMIN = "juari.neris@gmail.com"

# Configurações do Servidor SMTP
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "juari.neris@gmail.com"  
SMTP_PASS = "yins muld czac rcsi"

def inicializar_estado_login():
    """Inicializa as variáveis de sessão necessárias para a autenticação."""
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

    if "tela_atual" not in st.session_state:
        st.session_state.tela_atual = "login"

    if "usuarios_db" not in st.session_state:
        st.session_state.usuarios_db = {}

    if "solicitacoes_pendentes" not in st.session_state:
        st.session_state.solicitacoes_pendentes = {}

    if "email_recuperacao_temp" not in st.session_state:
        st.session_state.email_recuperacao_temp = ""

def validar_email(email: str) -> bool:
    padrao = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(padrao, email.strip()) is not None

def validar_senha_alfanumerica(senha: str) -> bool:
    """Valida se a senha possui exatamente 8 caracteres alfanuméricos."""
    return len(senha) == 8 and senha.isalnum() and not senha.isalpha() and not senha.isdigit()

def enviar_email_smtp(destinatario: str, assunto: str, corpo_html: str) -> tuple[bool, str]:
    """Envia um e-mail em formato HTML usando o servidor SMTP."""
    if "seu_email_sistema" in SMTP_USER or "sua_senha" in SMTP_PASS:
        return False, "As credenciais de remetente SMTP não foram preenchidas no código."

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = destinatario
    msg['Subject'] = assunto
    msg.attach(MIMEText(corpo_html, 'html'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, destinatario, msg.as_string())
        server.quit()
        return True, "E-mail enviado com sucesso!"
    except Exception as e:
        return False, str(e)

def enviar_alerta_aprovacao_admin(email_solicitante: str) -> tuple[bool, str]:
    """Gera os links de callback e envia a mensagem de aprovação para o administrador."""
    base_url = "https://barcode-prxfe2eu4o34ae9tpejqpc.streamlit.app" 
    
    link_aprovar = f"{base_url}/?acao=aprovar&user={email_solicitante}"
    link_recusar = f"{base_url}/?acao=recusar&user={email_solicitante}"
    
    corpo_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>Solicitação de Acesso ao Sistema de Patrimônio</h2>
        <p>O seguinte usuário solicitou a criação/alteração de acesso ao sistema:</p>
        <p><b>Usuário (E-mail):</b> {email_solicitante}</p>
        <p>Utilize uma das opções abaixo para autorizar ou rejeitar o cadastro:</p>
        <p style="margin-top: 20px;">
          <a href="{link_aprovar}" style="background-color: #28a745; color: white; padding: 10px 18px; text-decoration: none; border-radius: 4px; font-weight: bold; margin-right: 10px;">AUTORIZAR CADASTRO</a>
          <a href="{link_recusar}" style="background-color: #dc3545; color: white; padding: 10px 18px; text-decoration: none; border-radius: 4px; font-weight: bold;">RECUSAR CADASTRO</a>
        </p>
      </body>
    </html>
    """
    
    return enviar_email_smtp(
        destinatario=EMAIL_ADMIN,
        assunto="[AUTORIZAÇÃO NECESSÁRIA] Solicitação de Cadastro de Usuário",
        corpo_html=corpo_html
    )

def processar_query_params():
    """Processa ações recebidas via parâmetros de URL (aprovações e navegação)."""
    query_params = st.query_params

    if "page" in query_params:
        if query_params["page"] == "esqueci_senha":
            st.session_state.tela_atual = "esqueci_senha"
            st.query_params.clear()

    if "acao" in query_params and "user" in query_params:
        acao = query_params["acao"]
        usuario_alvo = query_params["user"]

        if usuario_alvo in st.session_state.solicitacoes_pendentes:
            senha_solicitada = st.session_state.solicitacoes_pendentes[usuario_alvo]
            if acao == "aprovar":
                st.session_state.usuarios_db[usuario_alvo] = senha_solicitada
                del st.session_state.solicitacoes_pendentes[usuario_alvo]
                st.success(f"Cadastro do usuário {usuario_alvo} APROVADO com sucesso!")
            elif acao == "recusar":
                del st.session_state.solicitacoes_pendentes[usuario_alvo]
                st.warning(f"Cadastro do usuário {usuario_alvo} RECUSADO!")
            st.query_params.clear()

def renderizar_login() -> bool:
    """
    Exibe a interface gráfica de Login/Recuperação de Senha.
    Retorna True se o usuário já estiver autenticado, ou False caso contrário.
    """
    inicializar_estado_login()
    processar_query_params()

    if st.session_state.autenticado:
        return True

    st.markdown("""
    <style>
    .stApp {
        background-color: #f7f9fc;
    }
    div.stButton > button {
        background-color: #595959;
        color: white;
        border: none;
        border-radius: 4px;
        width: 100%;
        padding: 10px;
    }
    div.stButton > button:hover {
        background-color: #404040;
        color: white;
    }
    .link-esqueci {
        color: #0066cc;
        text-decoration: underline;
        font-size: 14px;
        cursor: pointer;
        float: right;
    }
    </style>
    """, unsafe_allow_html=True)

    _, col_centro, _ = st.columns([1.5, 2, 1.5])

    with col_centro:
        col_logo_esq, col_logo_centro, col_logo_dir = st.columns([1, 2, 1])
        with col_logo_centro:
            try:
                st.image(URL_LOGO_GITHUB, use_container_width=True)
            except Exception:
                st.markdown(
                    """
                    <div style="text-align: center; margin-bottom: 20px;">
                        <h3 style="margin:0; padding:0; color:#000; font-family: sans-serif; font-size: 16px;">PREFEITURA MUNICIPAL DA</h3>
                        <h1 style="margin:0; padding:0; color:#000; font-family: sans-serif; font-size: 32px; font-weight: 900;">SERRA</h1>
                    </div>
                    """, unsafe_allow_html=True
                )
        st.write("")

        # ------------------------------------------
        # TELA 1: RECUPERAÇÃO DE SENHA
        # ------------------------------------------
        if st.session_state.tela_atual == "esqueci_senha":
            with st.container(border=True):
                st.markdown("<h3 style='text-align: center; color: #1a2b4c; margin-bottom: 20px; font-weight: 600;'>Esqueceu sua senha?</h3>", unsafe_allow_html=True)
                st.markdown("<p style='color: #555; text-align: left; font-size: 15px;'>Por favor, insira seu endereço de e-mail. Um e-mail será enviado a você, para que possa escolher uma nova senha.</p>", unsafe_allow_html=True)
                
                email_input = st.text_input("E-mail", placeholder="E-mail", key="input_recupera_email")
                
                st.write("")
                if st.button("📧 Enviar", key="btn_enviar_recuperacao"):
                    if validar_email(email_input):
                        st.session_state.email_recuperacao_temp = email_input.strip()
                        st.session_state.tela_atual = "formulario_senha"
                        st.rerun()
                    else:
                        st.error("Por favor, informe um endereço de e-mail válido.")

            st.markdown("<br>", unsafe_allow_html=True)
            col_voltar1, col_voltar2 = st.columns([1.2, 1])
            with col_voltar1:
                st.write("Esqueça, me envie de volta")
            with col_voltar2:
                if st.button("para a página de login.", key="btn_voltar_login"):
                    st.session_state.tela_atual = "login"
                    st.rerun()

        # ------------------------------------------
        # TELA 2: FORMULÁRIO DE CRIAÇÃO DE LOGIN/SENHA
        # ------------------------------------------
        elif st.session_state.tela_atual == "formulario_senha":
            with st.container(border=True):
                st.markdown("<h4 style='text-align: center; color: #1a2b4c; margin-bottom: 10px;'>Formulário de Acesso</h4>", unsafe_allow_html=True)
                st.info("Regra: O login deve ser um e-mail válido e a senha deve conter exatamente 8 caracteres alfanuméricos (letras e números).")
                
                email_login = st.text_input("Login (Endereço de E-mail)", value=st.session_state.email_recuperacao_temp)
                nova_senha = st.text_input("Nova Senha (8 caracteres alfanuméricos)", type="password", max_chars=8)
                confirma_senha = st.text_input("Confirme a Nova Senha", type="password", max_chars=8)

                if st.button("Enviar para Aprovação"):
                    if not validar_email(email_login):
                        st.error("O Login precisa ser um endereço de e-mail válido.")
                    elif not validar_senha_alfanumerica(nova_senha):
                        st.error("A senha deve possuir exatamente 8 caracteres alfanuméricos (contendo letras e números).")
                    elif nova_senha != confirma_senha:
                        st.error("As senhas digitadas não coincidem.")
                    else:
                        st.session_state.solicitacoes_pendentes[email_login.strip()] = nova_senha
                        sucesso_envio, msg_erro = enviar_alerta_aprovacao_admin(email_login.strip())
                        
                        if sucesso_envio:
                            st.success(f"Solicitação registrada! Um e-mail para autorização foi enviado com sucesso para **{EMAIL_ADMIN}**.")
                        else:
                            st.warning(f"Solicitação registrada internamente. Falha no disparo do e-mail SMTP: {msg_erro}")
                        
                        st.session_state.tela_atual = "login"

        # ------------------------------------------
        # TELA 3: LOGIN PRINCIPAL
        # ------------------------------------------
        else:
            with st.container(border=True):
                st.markdown("<h4 style='text-align: center; color: #1a2b4c; margin-bottom: 20px;'>Faça login na sua conta</h4>", unsafe_allow_html=True)
                st.divider()
                
                usuario = st.text_input("Usuário (E-mail)", value="", placeholder="Seu e-mail")
                
                col_label1, col_label2 = st.columns([1, 1])
                with col_label1:
                    st.markdown("<span style='font-size: 14px;'>Senha</span>", unsafe_allow_html=True)
                with col_label2:
                    st.markdown("<a href='?page=esqueci_senha' target='_self' class='link-esqueci'>Esqueceu sua senha?</a>", unsafe_allow_html=True)
                
                senha = st.text_input("Senha (oculto)", type="password", label_visibility="collapsed", placeholder="Sua senha")
                origem = st.selectbox("Origem de login", ["SERRA.LOCAL"])
                
                st.write("")
                if st.button("Entrar", key="btn_entrar"):
                    if usuario in st.session_state.usuarios_db and st.session_state.usuarios_db[usuario] == senha:
                        st.session_state.autenticado = True
                        st.rerun()
                    else:
                        st.error("Credenciais inválidas ou cadastro pendente de autorização por e-mail.")

    return False