# ==========================================
# 1. IMPORTAÇÕES DE BIBLIOTECAS
# ==========================================
import os
import numpy as np
import pandas as pd
import streamlit as st

# ==========================================
# 2. CONFIGURAÇÕES E CONSTANTES GLOBAIS
# ==========================================
ARQUIVO_EXCEL = "Tabela_Patrimonios_UBS_Feu_Rosa.xlsx"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/12mNKTWLExRwZx3EKSB78oTScQk6ctGvi6eNKt5QyXEw/edit?usp=sharing"

# Coluna primária de localização
COLUNA_CHAVE = "Local / Setor"

# Estrutura base de colunas padrão
COLUNAS_PADRAO = [
    COLUNA_CHAVE,
    "CPU",
    "Monitores",
    "Nobreak",
    "Teclado",
    "Mouse",
    "Impressora"
]

# Lista de colunas obsoletas a serem removidas na higienização
COLUNAS_OBSOLETAS = [
    "Patrimônio PC",
    "Patrimônio Tela",
    "Patrimônio Nobreak",
    "➕ Outra descrição (Criar nova coluna ao final)",
    "cameras"
]


# ==========================================
# 3. CONEXÃO COM GOOGLE SHEETS
# ==========================================
@st.cache_resource
def obter_conexao_gsheets():
    """Conecta com a API do Google Sheets via Streamlit GSheets Connection."""
    try:
        from streamlit_gsheets import GSheetsConnection
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception:
        return None

conn = obter_conexao_gsheets()


# ==========================================
# 4. MANIPULAÇÃO E HIGIENIZAÇÃO DE DADOS
# ==========================================
def padronizar_e_organizar_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Higieniza o DataFrame, remove colunas obsoletas, garante a coluna chave
    e organiza a ordem mantendo colunas padrão primeiro e dinâmicas depois.
    """
    # 1. Limpeza de colunas vazias ou obsoletas
    colunas_para_remover = [c for c in df.columns if c in COLUNAS_OBSOLETAS or c.startswith("➕") or "Unnamed" in c]
    if colunas_para_remover:
        df = df.drop(columns=colunas_para_remover, errors='ignore')

    # 2. Garante a coluna primária de Setor
    if COLUNA_CHAVE not in df.columns:
        df.insert(0, COLUNA_CHAVE, "")

    # 3. Assegura a presença das colunas padrão
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = ""

    # 4. Reorganiza a ordem mantendo as colunas padrão no início e dinâmicas no final
    outras_colunas = [c.strip() for c in df.columns if c not in COLUNAS_PADRAO]
    ordem_final = COLUNAS_PADRAO + outras_colunas
    
    # Normalização de tipos para string (evita perda de zeros em códigos de barra)
    df = df.reindex(columns=ordem_final).fillna("").astype(str)
    df[COLUNA_CHAVE] = df[COLUNA_CHAVE].str.strip()
    return df


def aplicar_estilo_excel(caminho_arquivo: str) -> None:
    """
    Aplica formatação visual profissional na planilha Excel (cores, bordas,
    largura adaptativa e alinhamento).
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    if not os.path.exists(caminho_arquivo):
        return

    wb = openpyxl.load_workbook(caminho_arquivo)
    ws = wb.active if 'Patrimônios' not in wb.sheetnames else wb['Patrimônios']

    # Paleta de Cores e Estilos
    header_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")  # Azul Marinho
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    
    row_fill_even = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    row_fill_odd = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    
    thin_border = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )
    
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")

    # 1. Formatação do Cabeçalho
    ws.row_dimensions[1].height = 28
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = thin_border

    # 2. Formatação das Linhas de Dados
    max_row = ws.max_row
    max_col = ws.max_column

    for r in range(2, max_row + 1):
        ws.row_dimensions[r].height = 22
        fill = row_fill_even if r % 2 == 0 else row_fill_odd
        for c in range(1, max_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.fill = fill
            cell.border = thin_border
            cell.font = Font(name="Segoe UI", size=10)
            cell.alignment = align_left if c == 1 else align_center
            # Força o formato texto na célula para preservar zeros à esquerda
            cell.number_format = '@'

    # 3. Auto-Ajuste Largura de Colunas
    for col in ws.columns:
        max_len = 0
        for cell in col:
            val = str(cell.value or '')
            if len(val) > max_len:
                max_len = len(val)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 5, 18)

    wb.save(caminho_arquivo)


# ==========================================
# 5. GERENCIAMENTO DE PERSISTÊNCIA E SINCRONIZAÇÃO
# ==========================================
@st.cache_data(ttl=60)
def carregar_dados_excel() -> tuple[pd.DataFrame, list[str]]:
    """Carrega os dados salvos localmente e retorna o DataFrame limpo e a lista de colunas."""
    if os.path.exists(ARQUIVO_EXCEL):
        try:
            df = pd.read_excel(ARQUIVO_EXCEL, sheet_name='Patrimônios', dtype=str, keep_default_na=False)
            if not df.empty and df.columns[0].startswith("Tabela de Patrimônios"):
                df = pd.read_excel(ARQUIVO_EXCEL, sheet_name='Patrimônios', header=1, dtype=str, keep_default_na=False)
            df = padronizar_e_organizar_df(df)
            return df, list(df.columns)
        except Exception as e:
            st.error(f"Erro ao carregar planilha local: {e}")
            
    df_empty = pd.DataFrame(columns=COLUNAS_PADRAO)
    df_empty = padronizar_e_organizar_df(df_empty)
    return df_empty, COLUNAS_PADRAO


def salvar_no_excel(df: pd.DataFrame) -> None:
    """Salva no Excel local, formata a planilha e sincroniza com o Google Sheets."""
    df = padronizar_e_organizar_df(df)
    
    # 1. Salva localmente
    try:
        with pd.ExcelWriter(ARQUIVO_EXCEL, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Patrimônios', index=False)
        aplicar_estilo_excel(ARQUIVO_EXCEL)
        carregar_dados_excel.clear()
    except Exception as e:
        st.error(f"Erro ao salvar arquivo Excel local: {e}")

    # 2. Sincroniza remotamente com o Google Sheets
    if conn is not None:
        try:
            conn.update(spreadsheet=GOOGLE_SHEET_URL, data=df)
            st.toast("☁️ Google Sheets sincronizado com sucesso!")
        except Exception as e:
            st.toast(f"⚠️ Salvo localmente. Erro no Google Sheets: {e}")


def adicionar_e_salvar(codigo: str, descricao: str, setor: str) -> None:
    """
    Sincroniza o código de barras no cruzamento exato do Setor e da Coluna selecionada no Menu.
    Cria novas colunas ou setores dinamicamente caso não existam.
    """
    df, _ = carregar_dados_excel()
    coluna_alvo = descricao.strip()
    setor_limpo = setor.strip() if setor else "Não informado"
    codigo_limpo = str(codigo).strip()
    
    # Sincronização da Coluna: Adiciona se for uma nova opção do menu
    if coluna_alvo not in df.columns:
        df[coluna_alvo] = ""
    
    df = padronizar_e_organizar_df(df)
    
    # Localização da Linha (Setor)
    mascara_setor = df[COLUNA_CHAVE].str.lower() == setor_limpo.lower()
    
    if mascara_setor.any():
        # Atualiza a célula existente
        idx = df[mascara_setor].index[0]
        df.at[idx, coluna_alvo] = codigo_limpo
    else:
        # Cria uma nova linha para o setor
        nova_linha = {col: "" for col in df.columns}
        nova_linha[COLUNA_CHAVE] = setor_limpo
        nova_linha[coluna_alvo] = codigo_limpo
        df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    
    df = padronizar_e_organizar_df(df)
    salvar_no_excel(df)
    st.session_state.df_historico = df


def sincronizar_estrutura_menus():
    """Garante que todos os setores e tipos de patrimônio dos menus existam na tabela."""
    df, _ = carregar_dados_excel()
    
    setores_menu = [
        "Consultório", "Gerência", "Administração", "Farmácia",
        "Almoxarifado", "Sala de Preparo", "Sala dos Agentes de Saúde",
        "Sala de Curativo", "Recepção", "Sala de Vacina"
    ]
    
    # 1. Garante que as colunas padrão (Tipos de Patrimônio) existam
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = ""
            
    # 2. Garante que as linhas (Setores Padrão) existam
    for setor in setores_menu:
        mascara_setor = df[COLUNA_CHAVE].str.lower() == setor.lower()
        if not mascara_setor.any():
            nova_linha = {col: "" for col in df.columns}
            nova_linha[COLUNA_CHAVE] = setor
            df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
            
    df = padronizar_e_organizar_df(df)
    
    # Salva e sincroniza com a URL do Google Sheets configurada
    salvar_no_excel(df) 
    st.session_state.df_historico = df


# ==========================================
# 6. PROCESSAMENTO DE IMAGEM (UPLOAD)
# ==========================================
def processar_imagem(image_file) -> tuple:
    import cv2
    import zxingcpp
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
        st.error(f"Erro no processamento da imagem: {e}")
        return None, []


# ==========================================
# 7. INTERFACE STREAMLIT
# ==========================================
def renderizar_card_inventario(lista_urs, lista_ubs):
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center;'>📦 Sistema de Inventários</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Acesse a ferramenta de gestão e leitura de códigos de barra.</p>", unsafe_allow_html=True)
        st.write("")

        urs_selecionada = st.selectbox("URS - Unidade Regional de Saúde", lista_urs, key="sel_urs_inv")
        ubs_selecionada = st.selectbox("UBS - Unidade Básica de Saúde", lista_ubs, key="sel_ubs_inv")

        unidade_escolhida = ""
        if urs_selecionada and not urs_selecionada.startswith("Selecione"):
            unidade_escolhida = urs_selecionada
        elif ubs_selecionada and not ubs_selecionada.startswith("Selecione"):
            unidade_escolhida = ubs_selecionada

        st.write("")
        if st.button("📂 Abrir Inventário", use_container_width=True, type="primary", key="btn_inventario"):
            st.session_state.unidade_selecionada = unidade_escolhida
            st.session_state.pagina_atual = "inventario"
            st.rerun()


def renderizar_sistema_inventario():
    df_inicial, _ = carregar_dados_excel()

    if "df_historico" not in st.session_state:
        st.session_state.df_historico = df_inicial

    if "saved_setor" not in st.session_state:
        st.session_state.saved_setor = ""

    if "saved_descricao" not in st.session_state:
        st.session_state.saved_descricao = ""

    st.title("📦 Sistema de Inventários - GTI-SESA")
    
    # Botão para forçar a criação dos cabeçalhos e linhas do menu no Google Sheets
    if st.button("🌐 Sincronizar Estrutura dos Menus com Google Sheets", type="secondary"):
        sincronizar_estrutura_menus()
        st.success("Cabeçalhos e setores sincronizados com sucesso na planilha online!")
        st.rerun()
        
    st.divider()

    unidade = st.session_state.get("unidade_selecionada", "")
    if unidade:
        st.subheader(f"🏥 Unidade: {unidade}")

    opcoes_setor = [
        "Consultório",
        "Gerência",
        "Administração",
        "Farmácia",
        "Almoxarifado",
        "Sala de Preparo",
        "Sala dos Agentes de Saúde",
        "Sala de Curativo",
        "Recepção",
        "Sala de Vacina",
        "➕ Outro Setor"
    ]

    # Alimenta o menu dinamicamente com as colunas reais já existentes na planilha
    colunas_df_atuais = [
        col for col in st.session_state.df_historico.columns 
        if col != COLUNA_CHAVE and col not in COLUNAS_OBSOLETAS
    ]

    opcoes_patrimonio = list(dict.fromkeys(colunas_df_atuais + [c for c in COLUNAS_PADRAO if c != COLUNA_CHAVE]))
    opcoes_patrimonio.append("➕ Outros Patrimônios")

    # --- Filtros e Seleção ---
    col_desc1, col_desc2, col_desc3 = st.columns([1, 1, 1])

    with col_desc1:
        idx_setor = 0
        if st.session_state.saved_setor in opcoes_setor:
            idx_setor = opcoes_setor.index(st.session_state.saved_setor)
        elif st.session_state.saved_setor:
            idx_setor = opcoes_setor.index("➕ Outro Setor")

        setor_selecionado = st.selectbox("Setor:", opcoes_setor, index=idx_setor, key="setor_selecionado_key")
        
        if setor_selecionado == "➕ Outro Setor":
            val_custom_setor = st.session_state.saved_setor if st.session_state.saved_setor not in opcoes_setor else ""
            setor_input = st.text_input("Nome do Setor:", value=val_custom_setor, placeholder="Ex: Raio-X...", key="setor_custom_key")
        else:
            setor_input = setor_selecionado
        st.session_state.saved_setor = setor_input

    with col_desc2:
        opcao_selecionada = st.selectbox("Tipo de patrimônio (Coluna):", opcoes_patrimonio, key="opcao_selecionada_key")

    with col_desc3:
        if opcao_selecionada == "➕ Outros Patrimônios":
            descricao_final = st.text_input("Nome da Nova Coluna:", placeholder="Ex: Servidor", key="descricao_nova_key")
        else:
            descricao_final = opcao_selecionada
        st.session_state.saved_descricao = descricao_final

    st.divider()

    if not descricao_final or not setor_input.strip():
        st.warning("⚠️ Preencha o **Setor** e o **Tipo de patrimônio** para habilitar o leitor.")
    else:
        tab_unificada, tab_upload = st.tabs(["⚡ Câmera / Scanner USB", "📁 Upload de Imagem"])

        # --- Aba 1: Leitor Câmera / USB ---
        with tab_unificada:
            st.markdown(f"📍 Setor Ativo: **`{setor_input}`** | Coluna Destino: **`{descricao_final}`**")
            col_camera, col_usb = st.columns([1.2, 1])

            with col_camera:
                st.caption("Aponte a câmera para o código de barras.")
                html_scanner = """
                <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
                <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
                <style>
                    #reader { width: 100% !important; max-width: 100% !important; border-radius: 12px; overflow: hidden; border: 2px solid #1B365D; background-color: #000; }
                    #reader video { object-fit: cover !important; border-radius: 10px; }
                    #scan-status { text-align: center; margin-top: 8px; font-weight: bold; color: #1B365D; font-family: sans-serif; font-size: 14px; }
                </style>
                <div class="scanner-wrapper">
                    <div id="reader"></div>
                    <div id="scan-status">📷 Inicializando câmera...</div>
                </div>
                <script>
                    let lastScannedCode = ""; let lastScannedTime = 0; let audioCtx = null;
                    function tocarBipNativo() {
                        try {
                            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                            if (audioCtx.state === 'suspended') audioCtx.resume();
                            const osc = audioCtx.createOscillator(); const gain = audioCtx.createGain();
                            osc.type = 'sine'; osc.frequency.setValueAtTime(1500, audioCtx.currentTime);
                            gain.gain.setValueAtTime(0.4, audioCtx.currentTime);
                            osc.connect(gain); gain.connect(audioCtx.destination);
                            osc.start(); osc.stop(audioCtx.currentTime + 0.12);
                        } catch(e) {}
                    }
                    function onScanSuccess(decodedText) {
                        const agora = Date.now();
                        if (decodedText === lastScannedCode && (agora - lastScannedTime) < 3000) return;
                        lastScannedCode = decodedText; lastScannedTime = agora;
                        tocarBipNativo();
                        document.getElementById('scan-status').innerText = "✅ Lido: " + decodedText + " (Salvando...)";
                        const parentDoc = window.parent.document;
                        const inputEl = parentDoc.querySelector('input[placeholder*="Aguardando bipagem"]');
                        if (inputEl) {
                            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                            nativeSetter.call(inputEl, decodedText);
                            inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                            setTimeout(() => {
                                const buttons = Array.from(parentDoc.querySelectorAll('button'));
                                const submitBtn = buttons.find(b => b.innerText.includes('Registrar Manualmente'));
                                if (submitBtn) submitBtn.click();
                            }, 150);
                        }
                    }
                    const html5QrCode = new Html5Qrcode("reader");
                    const config = { fps: 25, qrbox: { width: 250, height: 150 } };
                    html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess)
                    .then(() => { document.getElementById('scan-status').innerText = "📷 Leitor pronto. Aponte para o código."; })
                    .catch(() => { html5QrCode.start({ facingMode: "user" }, config, onScanSuccess); });
                </script>
                """
                st.components.v1.html(html_scanner, height=390)

            with col_usb:
                st.markdown("##### 🔌 Entrada Manual / Scanner USB")
                with st.form(key="form_bipagem", clear_on_submit=True):
                    codigo_input = st.text_input("Código Lido / Bipado:", autocomplete="off", placeholder="Aguardando bipagem...", key="input_codigo_bip")
                    btn_adicionar = st.form_submit_button("Registrar Manualmente", type="primary", use_container_width=True)
                    if btn_adicionar and codigo_input.strip():
                        adicionar_e_salvar(codigo_input.strip(), descricao_final, setor_input)
                        st.success(f"✅ Código `{codigo_input.strip()}` registrado na coluna **'{descricao_final}'** | Setor **'{setor_input}'**")
                        st.rerun()

        # --- Aba 2: Upload de Imagem ---
        with tab_upload:
            uploaded_file = st.file_uploader("Envie uma imagem do código de barras", type=["jpg", "png", "jpeg"])
            if uploaded_file is not None:
                img_processada, codigos_encontrados = processar_imagem(uploaded_file)
                col_img1, col_img2 = st.columns(2)
                with col_img1:
                    if img_processada is not None:
                        st.image(img_processada, caption="Imagem Analisada", use_container_width=True)
                with col_img2:
                    if codigos_encontrados:
                        st.success(f"{len(codigos_encontrados)} código(s) encontrado(s)!")
                        for item in codigos_encontrados:
                            adicionar_e_salvar(item['codigo'], descricao_final, setor_input)
                            st.write(f"**Código:** `{item['codigo']}` ➡️ Coluna: **{descricao_final}** | Setor: **{setor_input}**")
                        st.rerun()

    # --- Visualizador da Tabela Sincronizada ---
    st.divider()
    st.header("📊 Tabela de Patrimônios (Sincronizada)")
    df_atual, _ = carregar_dados_excel()
    if not df_atual.empty:
        st.dataframe(df_atual, use_container_width=True)
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            if st.button("🔄 Recarregar Dados", use_container_width=True):
                carregar_dados_excel.clear()
                st.rerun()
        with col_btn2:
            csv = df_atual.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="⬇️ Baixar Tabela (CSV)",
                data=csv,
                file_name="Tabela_Patrimonios_Sincronizada.csv",
                mime="text/csv",
                use_container_width=True
            )