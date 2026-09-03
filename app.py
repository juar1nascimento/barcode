import streamlit as st
import cv2
import numpy as np
from PIL import Image
import zxingcpp
import pandas as pd
import os
import hashlib
from streamlit_gsheets import GSheetsConnection
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Importação do módulo de login independente
from login import renderizar_login

# ==========================================
# CONFIGURAÇÕES DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Controle de Patrimônio - GTI-SESA",
    page_icon="📦",
    layout="wide"
)

# ==========================================
# VERIFICAÇÃO DE AUTENTICAÇÃO E LOGIN
# ==========================================
if not renderizar_login():
    st.stop()

# Inicialização da variável de navegação de páginas
if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "portal"

# ==========================================
# BARRA LATERAL (MENU E LOGOUT)
# ==========================================
with st.sidebar:
    st.markdown("### 👤 Usuário Autenticado")
    
    if st.session_state.pagina_atual == "inventario":
        if st.button("🏠 Voltar ao Portal"):
            st.session_state.pagina_atual = "portal"
            st.rerun()

    if st.button("🚪 Sair do Sistema"):
        st.session_state.autenticado = False
        st.session_state.pagina_atual = "portal"
        st.rerun()

# ==========================================
# TELA INTERMEDIÁRIA (PORTAL DE SERVIÇOS)
# ==========================================
if st.session_state.pagina_atual == "portal":
    st.title("🖥️ Portal de Sistemas GTI-SESA")
    st.markdown("Bem-vindo ao painel central de aplicações. Escolha o sistema que deseja acessar:")
    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        with st.container(border=True):
            st.markdown("<h3 style='text-align: center;'>📦 Módulo de Inventário</h3>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #666;'>Acesse a ferramenta de gestão, leitura de códigos de barra e controle de patrimônio.</p>", unsafe_allow_html=True)
            st.write("")

            st.link_button(
                "🚀 Acessar Sistema de Inventários (Link Externo)",
                "https://barcode-prxfe2eu4o34ae9tpejqpc.streamlit.app/",
                use_container_width=True,
                type="primary"
            )

            st.write("")
            
            if st.button("📂 Abrir Inventário nesta Aba", use_container_width=True):
                st.session_state.pagina_atual = "inventario"
                st.rerun()

    st.stop()

# ==========================================
# CONFIGURAÇÕES E CONSTANTES DO SISTEMA DE INVENTÁRIO
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

def processar_imagem(image_file) -> tuple:
    try:
        if hasattr(image_file, 'getvalue'):
            file_bytes = np.frombuffer(image_file.getvalue(), dtype=np.uint8)
        else:
            file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is None:
            return None, []

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        barcodes = zxingcpp.read_barcodes(img_rgb)
        resultados = []

        for barcode in barcodes:
            if hasattr(barcode, 'position') and barcode.position:
                try:
                    pos = barcode.position
                    if hasattr(pos, 'top_left'):
                        pts_list = [
                            [int(pos.top_left.x), int(pos.top_left.y)],
                            [int(pos.top_right.x), int(pos.top_right.y)],
                            [int(pos.bottom_right.x), int(pos.bottom_right.y)],
                            [int(pos.bottom_left.x), int(pos.bottom_left.y)]
                        ]
                    else:
                        pts_list = [[int(getattr(pt, 'x', pt[0])), int(getattr(pt, 'y', pt[1]))] for pt in pos]

                    if pts_list:
                        pts = np.array(pts_list, np.int32).reshape((-1, 1, 2))
                        cv2.polylines(img_rgb, [pts], True, (0, 255, 0), 3)
                except Exception:
                    pass

            resultados.append({
                "codigo": barcode.text, 
                "tipo": str(barcode.format).replace("BarcodeFormat.", "")
            })

        return img_rgb, resultados
    except Exception as e:
        st.error(f"Erro ao processar imagem: {e}")
        return None, []

# ==========================================
# INICIALIZAÇÃO DO ESTADO DA SESSÃO DO INVENTÁRIO
# ==========================================
df_inicial, colunas_iniciais = carregar_dados_excel()

if "df_historico" not in st.session_state:
    st.session_state.df_historico = df_inicial

if "saved_setor" not in st.session_state:
    st.session_state.saved_setor = ""

if "saved_descricao" not in st.session_state:
    st.session_state.saved_descricao = ""

# ==========================================
# INTERFACE DO USUÁRIO (SISTEMA DE INVENTÁRIO)
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
    setor_input = st.text_input("Local / Setor:", value=st.session_state.saved_setor, placeholder="Ex: Consultório 1, Recepção...", key="setor_input_key")
    st.session_state.saved_setor = setor_input

with col_desc2:
    opcao_selecionada = st.selectbox(
        "Selecione a coluna de destino:",
        opcoes_patrimonio,
        key="opcao_selecionada_key"
    )

with col_desc3:
    if opcao_selecionada == "➕ Outra descrição (Criar nova coluna ao final)":
        descricao_final = st.text_input("Digite o nome da nova coluna:", placeholder="Ex: Patrimônio Impressora", key="descricao_nova_key")
    else:
        descricao_final = opcao_selecionada
    
    st.session_state.saved_descricao = descricao_final

st.divider()

# --- PROCESSA BEEP VIA QUERY PARAMS ---
query_params = st.query_params
if "scanned_code" in query_params:
    codigo_auto = query_params.get("scanned_code")
    setor_param = query_params.get("setor", st.session_state.saved_setor)
    descricao_param = query_params.get("coluna", st.session_state.saved_descricao)
    
    st.query_params.clear()  # Limpa o parâmetro da URL imediatamente
    
    if codigo_auto and setor_param.strip() and descricao_param.strip():
        adicionar_e_salvar(codigo_auto, descricao_param, setor_param)
        st.toast(f"⚡ Código `{codigo_auto}` bipado e registrado com sucesso!", icon="✅")
        st.rerun()

# --- CAPTURA E REGISTRO ---
st.subheader("2. Realize a Leitura do Código")

if not descricao_final or not setor_input.strip():
    st.warning("⚠️ Por favor, preencha o **Local / Setor** e selecione ou informe a **Descrição** antes de realizar a leitura.")
else:
    tab_unificada, tab_upload = st.tabs([
        "🔌 Leitor USB Bematech / Digitação / 📱 Câmera Automática", 
        "📁 Upload de Imagem"
    ])

    # ==========================================
    # ABA UNIFICADA: SCANNER USB, DIGITAÇÃO E CÂMERA AUTOMÁTICA
    # ==========================================
    with tab_unificada:
        st.markdown(f"Registrando para o setor **`{setor_input}`** na coluna: **`{descricao_final}`**")
        
        col_usb, col_camera = st.columns(2)

        # BLOCO 1: Leitor USB Bematech / Digitação Manual
        with col_usb:
            st.markdown("##### 🔌 Bipagem Scanner USB / Digitação Manual")
            with st.form(key="form_bipagem", clear_on_submit=True):
                codigo_input = st.text_input(
                    "Bipe com o scanner Bematech BR-310 ou digite:", 
                    autocomplete="off",
                    placeholder="Aguardando bipagem do scanner...",
                    key="input_codigo_bip"
                )
                btn_adicionar = st.form_submit_button("Registrar Manualmente", type="primary", use_container_width=True)

                if btn_adicionar and codigo_input.strip():
                    adicionar_e_salvar(codigo_input.strip(), descricao_final, setor_input)
                    st.success(f"✅ Código `{codigo_input.strip()}` registrado em **'{descricao_final}'**!")

        # BLOCO 2: Bipagem Automática pela Câmera (Sem Clicar)
        with col_camera:
            st.markdown("##### 📱 Bipagem Automática via Câmera do Celular")
            st.caption("Aproxime a câmera do código de barras. A leitura e gravação acontecem instantaneamente.")

            # Componente de Leitura Contínua via HTML5-QRCode
            html_scanner = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
                <style>
                    #reader {{
                        width: 100%;
                        max-width: 450px;
                        margin: 0 auto;
                        border-radius: 8px;
                        overflow: hidden;
                        border: 2px solid #1F4E78;
                    }}
                    #reader video {{
                        object-fit: cover;
                    }}
                </style>
            </head>
            <body>
                <div id="reader"></div>
                <script>
                    let lastCode = "";
                    let lastTime = 0;

                    function emitBeep() {{
                        try {{
                            const ctx = new (window.AudioContext || window.webkitAudioContext)();
                            const osc = ctx.createOscillator();
                            const gain = ctx.createGain();
                            osc.type = "sine";
                            osc.frequency.value = 1200;
                            gain.gain.value = 0.25;
                            osc.connect(gain);
                            gain.connect(ctx.destination);
                            osc.start();
                            setTimeout(() => osc.stop(), 120);
                        }} catch(e) {{ console.log(e); }}
                    }}

                    function onScanSuccess(decodedText, decodedResult) {{
                        const now = Date.now();
                        // Evita bipar o mesmo código repetidamente dentro de 3 segundos
                        if (decodedText === lastCode && (now - lastTime) < 3000) {{
                            return;
                        }}
                        lastCode = decodedText;
                        lastTime = now;

                        emitBeep();

                        // Envia o parâmetro via URL principal com setor e coluna embutidos
                        try {{
                            const topUrl = new URL(window.top.location.href);
                            topUrl.searchParams.set("scanned_code", decodedText);
                            topUrl.searchParams.set("setor", encodeURIComponent("{setor_input.strip()}"));
                            topUrl.searchParams.set("coluna", encodeURIComponent("{descricao_final.strip()}"));
                            topUrl.searchParams.set("ts", now);
                            window.top.location.href = topUrl.toString();
                        }} catch(e) {{
                            window.parent.postMessage({{ type: "scanned_code", value: decodedText }}, "*");
                        }}
                    }}

                    const html5QrCode = new Html5Qrcode("reader");
                    const config = {{ 
                        fps: 15, 
                        qrbox: {{ width: 260, height: 150 }},
                        aspectRatio: 1.333333
                    }};

                    html5QrCode.start(
                        {{ facingMode: "environment" }}, 
                        config, 
                        onScanSuccess
                    ).catch(err => {{
                        document.getElementById("reader").innerHTML = 
                            "<p style='color:#721c24; background-color:#f8d7da; padding:12px; border-radius:5px; text-align:center;'>⚠️ Permita o acesso à câmera no navegador para realizar a bipagem automática.</p>";
                    }});
                </script>
            </body>
            </html>
            """
            st.components.v1.html(html_scanner, height=360)

        # Script JS: Cancela atalhos do leitor USB e mantém o foco no input
        st.components.v1.html(
            """
            <script>
                (function() {
                    const parentDoc = window.parent.document;

                    function fixarFocoInput() {
                        const inputs = parentDoc.querySelectorAll('input[type="text"]');
                        for (let input of inputs) {
                            if (input.placeholder && input.placeholder.includes("Aguardando bipagem")) {
                                input.focus();
                                break;
                            }
                        }
                    }

                    fixarFocoInput();
                    setTimeout(fixarFocoInput, 150);
                    setTimeout(fixarFocoInput, 400);

                    if (!window.parent._bematech_listener_added) {
                        window.parent._bematech_listener_added = true;
                        parentDoc.addEventListener('keydown', function(e) {
                            if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S' || e.key === 'd' || e.key === 'D' || e.key === 'j' || e.key === 'J')) {
                                e.preventDefault();
                                e.stopPropagation();
                            }
                        }, true);
                    }
                })();
            </script>
            """,
            height=0
        )

    # ==========================================
    # ABA SECUNDÁRIA: UPLOAD DE IMAGEM
    # ==========================================
    with tab_upload:
        st.markdown(f"Registrando para o setor **`{setor_input}`** na coluna: **`{descricao_final}`**")
        uploaded_file = st.file_uploader("Escolha uma imagem contendo o código", type=["jpg", "png", "jpeg"])

        if uploaded_file is not None:
            img_processada, codigos_encontrados = processar_imagem(uploaded_file)
            
            col_img1, col_img2 = st.columns(2)
            with col_img1:
                if img_processada is not None:
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