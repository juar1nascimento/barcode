import streamlit as st
import cv2
import numpy as np
from PIL import Image
import zxingcpp
import pandas as pd
import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from streamlit_gsheets import GSheetsConnection
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ==========================================
# CONFIGURAÇÕES DA PÁGINA (Deve ser o 1º comando)
# ==========================================
st.set_page_config(
    page_title="Controle de Patrimônio - UBS Feu Rosa",
    page_icon="📦",
    layout="wide"
)

# Caminho da imagem de logo e E-mail do Administrador
CAMINHO_LOGO = r"D:\Usuários\juari.nascimento\Documents\Projetos\Inventários\barcode-app\imagens\image_6ca286.png"
EMAIL_ADMIN = "juari.nascimento@serra.es.gov.br"

# Configurações do Servidor SMTP
# NOTA: O endereço smtp.serra.es.gov.br só funciona dentro da rede interna da prefeitura.
# Para o Streamlit Cloud na Web, utilize um SMTP externo válido ou altere as credenciais.
SMTP_SERVER = "smtp.serra.es.gov.br"
SMTP_PORT = 587
SMTP_USER = "seu_email_sistema@serra.es.gov.br"  
SMTP_PASS = "sua_senha_ou_token"

# ==========================================
# GERENCIAMENTO DE ESTADO DA SESSÃO
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if "tela_atual" not in st.session_state:
    st.session_state.tela_atual = "login"

# Base de usuários cadastrados
if "usuarios_db" not in st.session_state:
    st.session_state.usuarios_db = {
        "juari.nascimento@serra.es.gov.br": "abc12345"
    }

# Fila de solicitações pendentes de aprovação
if "solicitacoes_pendentes" not in st.session_state:
    st.session_state.solicitacoes_pendentes = {}

# E-mail temporário em processo de recuperação
if "email_recuperacao_temp" not in st.session_state:
    st.session_state.email_recuperacao_temp = ""

# ==========================================
# PROCESSAMENTO DE APROVAÇÃO/RECUSA VIA LINK DE E-MAIL
# ==========================================
query_params = st.query_params
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

# ==========================================
# FUNÇÕES AUXILIARES DE VALIDAÇÃO E E-MAIL REAL
# ==========================================
def validar_email(email: str) -> bool:
    padrao = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(padrao, email.strip()) is not None

def validar_senha_alfanumerica(senha: str) -> bool:
    """Valida se a senha possui exatamente 8 caracteres alfanuméricos."""
    return len(senha) == 8 and senha.isalnum() and not senha.isalpha() and not senha.isdigit()

def enviar_email_smtp(destinatario: str, assunto: str, corpo_html: str) -> bool:
    """Envia um e-mail em formato HTML usando o servidor SMTP."""
    if "seu_email_sistema" in SMTP_USER:
        st.warning("⚠️ As credenciais de SMTP_USER/SMTP_PASS não foram configuradas.")
        return False

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
        return True
    except Exception as e:
        st.error(f"Erro no envio do e-mail via SMTP: {e}")
        return False

def enviar_alerta_aprovacao_admin(email_solicitante: str) -> bool:
    """Gera os links de callback e envia a mensagem para o e-mail do administrador."""
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
    
    sucesso = enviar_email_smtp(
        destinatario=EMAIL_ADMIN,
        assunto="[AUTORIZAÇÃO NECESSÁRIA] Solicitação de Cadastro de Usuário",
        corpo_html=corpo_html
    )

    # Caso o envio via rede falhe, permite ao administrador testar a aprovação localmente
    if not sucesso:
        st.info("💡 **Aprovação Direta (Modo de Contingência Cloud):**")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"[✅ Aprovar {email_solicitante}]({link_aprovar})")
        with col2:
            st.markdown(f"[❌ Recusar {email_solicitante}]({link_recusar})")

    return sucesso

# ==========================================
# SISTEMA DE AUTENTICAÇÃO E RECUPERAÇÃO DE ACESSO
# ==========================================
if not st.session_state.autenticado:
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
    </style>
    """, unsafe_allow_html=True)

    _, col_centro, _ = st.columns([1.5, 2, 1.5])

    with col_centro:
        col_logo_esq, col_logo_centro, col_logo_dir = st.columns([1, 2, 1])
        with col_logo_centro:
            if os.path.exists(CAMINHO_LOGO):
                st.image(CAMINHO_LOGO, use_container_width=True)
            else:
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
                        enviado = enviar_alerta_aprovacao_admin(email_login.strip())
                        
                        if enviado:
                            st.success(f"Solicitação registrada! Um e-mail para autorização foi direcionado para **{EMAIL_ADMIN}**.")
                        else:
                            st.warning("Solicitação pendente registrada internamente no sistema.")

        # ------------------------------------------
        # TELA 3: LOGIN PRINCIPAL
        # ------------------------------------------
        else:
            with st.container(border=True):
                st.markdown("<h4 style='text-align: center; color: #1a2b4c; margin-bottom: 20px;'>Faça login na sua conta</h4>", unsafe_allow_html=True)
                st.divider()
                
                usuario = st.text_input("Usuário (E-mail)", value="juari.nascimento@serra.es.gov.br")
                
                col_label1, col_label2 = st.columns([1, 1])
                with col_label1:
                    st.markdown("<span style='font-size: 14px;'>Senha</span>", unsafe_allow_html=True)
                with col_label2:
                    if st.button("Esqueceu sua senha?", key="link_esqueci_texto", type="tertiary"):
                        st.session_state.tela_atual = "esqueci_senha"
                        st.rerun()
                
                senha = st.text_input("Senha (oculto)", type="password", label_visibility="collapsed")
                origem = st.selectbox("Origem de login", ["SERRA.LOCAL"])
                
                st.write("")
                if st.button("Entrar", key="btn_entrar"):
                    if usuario in st.session_state.usuarios_db and st.session_state.usuarios_db[usuario] == senha:
                        st.session_state.autenticado = True
                        st.rerun()
                    else:
                        st.error("Credenciais inválidas ou cadastro pendente de autorização por e-mail.")

    st.stop()

# ==========================================
# CONFIGURAÇÕES E CONSTANTES DO APP PRINCIPAL
# ==========================================
ARQUIVO_EXCEL = "Tabela_Patrimonios_UBS_Feu_Rosa.xlsx"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/12mNKTWLExRwZx3EKSB78oTScQk6ctGvi6eNKt5QyXEw/edit?usp=sharing"

COLUNAS_PADRAO = ["Local / Setor", "Patrimônio PC", "Patrimônio Tela", "Patrimônio Nobreak"]

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception:
    conn = None

# ==========================================
# FUNÇÕES DE ESTILIZAÇÃO E MANIPULAÇÃO
# ==========================================
def padronizar_e_organizar_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = ""

    outras_colunas = [c for c in df.columns if c not in COLUNAS_PADRAO]
    ordem_final = COLUNAS_PADRAO + outras_colunas

    return df[ordem_final].fillna("").astype(str)

def aplicar_estilo_excel(caminho_arquivo: str) -> None:
    wb = openpyxl.load_workbook(caminho_arquivo)
    ws = wb['Patrimônios']

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    
    row_fill_even = PatternFill(start_color="F2F4F7", end_color="F2F4F7", fill_type="solid")
    row_fill_odd = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = thin_border
    ws.row_dimensions[1].height = 28

    max_row = ws.max_row
    max_col = ws.max_column

    for r in range(2, max_row + 1):
        ws.row_dimensions[r].height = 22
        fill = row_fill_even if r % 2 == 0 else row_fill_odd
        for c in range(1, max_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.fill = fill
            cell.border = thin_border
            cell.font = Font(name="Calibri", size=10)
            cell.alignment = align_left if c == 1 else align_center

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 5, 18)

    wb.save(caminho_arquivo)

def carregar_dados_excel() -> tuple[pd.DataFrame, list[str]]:
    if os.path.exists(ARQUIVO_EXCEL):
        try:
            df = pd.read_excel(ARQUIVO_EXCEL, sheet_name='Patrimônios', dtype=str, keep_default_na=False)
            
            if not df.empty and df.columns[0].startswith("Tabela de Patrimônios"):
                df = pd.read_excel(ARQUIVO_EXCEL, sheet_name='Patrimônios', header=1, dtype=str, keep_default_na=False)

            df = df.dropna(how='all')
            df = padronizar_e_organizar_df(df)
            return df, list(df.columns)
        except Exception as e:
            st.error(f"Erro ao carregar a planilha existente: {e}")
    
    df_empty = pd.DataFrame(columns=COLUNAS_PADRAO)
    df_empty = padronizar_e_organizar_df(df_empty)
    return df_empty, COLUNAS_PADRAO

def salvar_no_excel(df: pd.DataFrame) -> None:
    df = padronizar_e_organizar_df(df)
    
    try:
        with pd.ExcelWriter(ARQUIVO_EXCEL, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Patrimônios', index=False)
        aplicar_estilo_excel(ARQUIVO_EXCEL)
    except Exception as e:
        st.error(f"Erro ao salvar e formatar a planilha local: {e}")

    if conn is not None:
        try:
            conn.update(
                spreadsheet=GOOGLE_SHEET_URL,
                data=df
            )
            st.toast("☁️ Dados e formatação sincronizados no Google Sheets!")
        except Exception as e:
            st.error(f"Falha na sincronização com Google Sheets: {e}")

def adicionar_e_salvar(codigo: str, descricao: str, setor: str) -> None:
    df, _ = carregar_dados_excel()
    
    coluna_alvo = descricao.strip()
    setor_limpo = setor.strip() if setor else "Não informado"
    codigo_limpo = str(codigo).strip()
    
    if coluna_alvo not in df.columns:
        df[coluna_alvo] = ""
    
    df = padronizar_e_organizar_df(df)
    
    df["Local / Setor"] = df["Local / Setor"].str.strip()
    mascara_setor = df["Local / Setor"].str.lower() == setor_limpo.lower()
    
    if mascara_setor.any():
        idx = df[mascara_setor].index[0]
        df.at[idx, coluna_alvo] = codigo_limpo
    else:
        nova_linha = {col: "" for col in df.columns}
        nova_linha["Local / Setor"] = setor_limpo
        nova_linha[coluna_alvo] = codigo_limpo
        
        df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    
    df = padronizar_e_organizar_df(df)
    salvar_no_excel(df)
    st.session_state.df_historico = df

def processar_imagem(image_bytes) -> tuple:
    file_bytes = np.asarray(bytearray(image_bytes.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    barcodes = zxingcpp.read_barcodes(img_rgb)
    resultados = []

    for barcode in barcodes:
        if barcode.position:
            pts = np.array([[pt.x, pt.y] for pt in barcode.position], np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(img_rgb, [pts], True, (0, 255, 0), 3)

        resultados.append({
            "codigo": barcode.text, 
            "tipo": str(barcode.format).replace("BarcodeFormat.", "")
        })

    return img_rgb, resultados

# ==========================================
# INICIALIZAÇÃO DO ESTADO DA SESSÃO
# ==========================================
df_inicial, colunas_iniciais = carregar_dados_excel()

if "df_historico" not in st.session_state:
    st.session_state.df_historico = df_inicial

# ==========================================
# INTERFACE DO USUÁRIO (FRONTEND)
# ==========================================
st.title("📦 Sistema de Controle de Patrimônio GTI-SESA")
st.markdown(f"**Sincronização Ativa:** Salvando em `{ARQUIVO_EXCEL}` e no **Google Sheets**")
st.divider()

# --- SELEÇÃO DE COLUNA / DESCRIÇÃO ---
st.subheader("1. Selecione ou Digite a Descrição do Patrimônio")

opcoes_patrimonio = [col for col in st.session_state.df_historico.columns if col != "Local / Setor"]
opcoes_patrimonio.append("➕ Outra descrição (Criar nova coluna ao final)")

col_desc1, col_desc2, col_desc3 = st.columns(3)

with col_desc1:
    setor_input = st.text_input("Local / Setor:", placeholder="Ex: Consultório 1, Recepção...")

with col_desc2:
    opcao_selecionada = st.selectbox(
        "Selecione a coluna de destino:",
        opcoes_patrimonio
    )

with col_desc3:
    if opcao_selecionada == "➕ Outra descrição (Criar nova coluna ao final)":
        descricao_final = st.text_input("Digite o nome da nova coluna:", placeholder="Ex: Patrimônio Impressora")
    else:
        descricao_final = opcao_selecionada

st.divider()

# --- CAPTURA E REGISTRO ---
st.subheader("2. Realize a Leitura do Código")

if not descricao_final or not setor_input.strip():
    st.warning("⚠️ Por favor, preencha o **Local / Setor** e selecione ou informe a **Descrição** antes de realizar a leitura.")
else:
    tab_manual, tab_webcam, tab_upload = st.tabs([
        "⌨️ Digitação / Leitor USB", 
        "📷 Captura via Webcam", 
        "📁 Upload de Imagem"
    ])

    with tab_manual:
        st.markdown(f"Registrando para o setor **`{setor_input}`** na coluna: **`{descricao_final}`**")
        with st.form(key="form_manual", clear_on_submit=True):
            codigo_input = st.text_input("Digite ou bipe o código de barras:", autocomplete="off")
            btn_adicionar = st.form_submit_button("Registrar na Tabela")

            if btn_adicionar and codigo_input.strip():
                adicionar_e_salvar(codigo_input.strip(), descricao_final, setor_input)
                st.success(f"✅ Código `{codigo_input.strip()}` registrado na coluna **'{descricao_final}'** do setor **'{setor_input}'**!")

    with tab_webcam:
        st.markdown(f"Registrando para o setor **`{setor_input}`** na coluna: **`{descricao_final}`**")
        camera_image = st.camera_input("Tire uma foto focada no código de barras")

        if camera_image:
            img_processada, codigos_encontrados = processar_imagem(camera_image)
            
            col_img1, col_img2 = st.columns(2)
            with col_img1:
                st.image(img_processada, caption="Imagem Processada", use_container_width=True)
            
            with col_img2:
                if codigos_encontrados:
                    st.success(f"{len(codigos_encontrados)} código(s) detectado(s)!")
                    for item in codigos_encontrados:
                        adicionar_e_salvar(item['codigo'], descricao_final, setor_input)
                        st.write(f"**Código:** `{item['codigo']}` ➡️ Coluna: **{descricao_final}**")
                else:
                    st.warning("Nenhum código legível encontrado.")

    with tab_upload:
        st.markdown(f"Registrando para o setor **`{setor_input}`** na coluna: **`{descricao_final}`**")
        uploaded_file = st.file_uploader("Escolha uma imagem contendo o código", type=["jpg", "png", "jpeg"])

        if uploaded_file is not None:
            img_processada, codigos_encontrados = processar_imagem(uploaded_file)
            
            col_img1, col_img2 = st.columns(2)
            with col_img1:
                st.image(img_processada, caption="Imagem Processada", use_container_width=True)
                
            with col_img2:
                if codigos_encontrados:
                    st.success(f"{len(codigos_encontrados)} código(s) detectado(s)!")
                    for item in codigos_encontrados:
                        adicionar_e_salvar(item['codigo'], descricao_final, setor_input)
                        st.write(f"**Código:** `{item['codigo']}` ➡️ Coluna: **{descricao_final}**")
                else:
                    st.error("Nenhum código de barras identificado.")

# ==========================================
# EXIBIÇÃO DA TABELA ATUALIZADA
# ==========================================
st.divider()
st.header("📊 Tabela de Patrimônios Atualizada em Tempo Real")

df_atual, _ = carregar_dados_excel()
if not df_atual.empty:
    df_exibicao = df_atual.fillna("").astype(str)
    st.dataframe(df_exibicao, use_container_width=True)

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        if st.button("Recarregar Planilha"):
            st.rerun()
            
    with col_btn2:
        csv = df_atual.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Baixar Tabela Completa (CSV)",
            data=csv,
            file_name="Tabela_Patrimonios_UBS_Feu_Rosa.csv",
            mime="text/csv"
        )
else:
    st.info("A planilha está sem registros.")