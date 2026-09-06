# ==============================================================================
# 1. IMPORTAÇÕES DE BIBLIOTECAS E DEPENDÊNCIAS
# ==============================================================================
import os
from typing import Optional, Tuple, List, Dict, Any

import numpy as np
import pandas as pd
import streamlit as st

# ==============================================================================
# 2. CONFIGURAÇÕES E CONSTANTES GLOBAIS
# ==============================================================================
ARQUIVO_EXCEL: str = "Tabela_Patrimonios_UBS_Feu_Rosa.xlsx"
GOOGLE_SHEET_URL: str = "https://docs.google.com/spreadsheets/d/12mNKTWLExRwZx3EKSB78oTScQk6ctGvi6eNKt5QyXEw/edit?usp=sharing"
NOME_ABA_GSHEETS: str = "Patrimônios"

# Coluna primária referente ao setor/localização
COLUNA_CHAVE: str = "Local / Setor"

# Estrutura inicial e padrão de colunas da planilha
COLUNAS_PADRAO: List[str] = [
    COLUNA_CHAVE,
    "CPU",
    "Monitores",
    "Nobreak",
    "Teclado",
    "Mouse",
    "Impressora"
]

# Lista de colunas obsoletas ou temporárias a serem desconsideradas/removidas
COLUNAS_OBSOLETAS: List[str] = [
    "Patrimônio PC",
    "Patrimônio Tela",
    "Patrimônio Nobreak",
    "➕ Outra descrição (Criar nova coluna ao final)",
    "cameras"
]

# Setores pré-definidos para preenchimento rápido no formulário
SETORES_PADRAO: List[str] = [
    "Consultório", "Gerência", "Administração", "Farmácia",
    "Almoxarifado", "Sala de Preparo", "Sala dos Agentes de Saúde",
    "Sala de Curativo", "Recepção", "Sala de Vacina"
]

# ==============================================================================
# 3. GERENCIAMENTO DE CONEXÃO REMOTA (GOOGLE SHEETS)
# ==============================================================================
@st.cache_resource
def obter_conexao_gsheets() -> Optional[Any]:
    """Estabelece a conexão com a API do Google Sheets via Streamlit GSheets Connection."""
    try:
        from streamlit_gsheets import GSheetsConnection
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception as err:
        st.caption(f"⚠️ Módulo GSheetsConnection indisponível: {err}")
        return None

conn = obter_conexao_gsheets()

# ==============================================================================
# 4. MANIPULAÇÃO E TRATAMENTO SIMPLIFICADO DE DADOS
# ==============================================================================
def padronizar_e_organizar_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Higieniza o DataFrame mantendo estritamente a estrutura simples de dados:
    1. Remove colunas obsoletas.
    2. Garante a coluna do setor e colunas padrão.
    3. Reordena as colunas e converte valores em strings limpas.
    """
    colunas_invisiveis = [
        c for c in df.columns 
        if c in COLUNAS_OBSOLETAS or str(c).startswith("➕") or "Unnamed" in str(c)
    ]
    if colunas_invisiveis:
        df = df.drop(columns=colunas_invisiveis, errors="ignore")

    if COLUNA_CHAVE not in df.columns:
        df.insert(0, COLUNA_CHAVE, "")

    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = ""

    outras_colunas = [str(c).strip() for c in df.columns if c not in COLUNAS_PADRAO]
    ordem_final = COLUNAS_PADRAO + outras_colunas
    
    df_processado = df.reindex(columns=ordem_final).fillna("").astype(str)
    df_processado[COLUNA_CHAVE] = df_processado[COLUNA_CHAVE].str.strip()
    
    return df_processado


def aplicar_estilo_excel(caminho_arquivo: str) -> None:
    """
    Aplica formatação corporativa moderna na planilha Excel local:
    - Cabeçalho Navy escuro com texto branco.
    - Zebra striping (linhas alternadas em cinza suave).
    - Bordas suaves e alinhamento profissional.
    - Largura adaptativa das colunas.
    """
    if not os.path.exists(caminho_arquivo):
        return

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.load_workbook(caminho_arquivo)
        ws = wb[NOME_ABA_GSHEETS] if NOME_ABA_GSHEETS in wb.sheetnames else wb.active

        # Estilos Corporativos
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        
        row_even_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        row_odd_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        col_chave_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        thin_border_side = Side(border_style="thin", color="CBD5E1")
        border_box = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")
        font_data = Font(name="Segoe UI", size=10, color="0F172A")
        font_sector = Font(name="Segoe UI", size=10, bold=True, color="0F172A")

        # Configurar Cabeçalho
        ws.row_dimensions[1].height = 28
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align_center
            cell.border = border_box

        # Configurar Linhas de Dados
        for r in range(2, ws.max_row + 1):
            ws.row_dimensions[r].height = 22
            current_fill = row_odd_fill if r % 2 == 1 else row_even_fill

            for c in range(1, ws.max_column + 1):
                cell = ws.cell(row=r, column=c)
                cell.border = border_box
                cell.number_format = "@"

                if c == 1:
                    cell.fill = col_chave_fill
                    cell.font = font_sector
                    cell.alignment = align_left
                else:
                    cell.fill = current_fill
                    cell.font = font_data
                    cell.alignment = align_center

        # Autoadaptar Largura de Colunas
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 5, 16)

        wb.save(caminho_arquivo)
    except Exception as e:
        st.warning(f"Aviso de formatação no Excel local: {e}")

# ==============================================================================
# 5. PERSISTÊNCIA DE DADOS, SINCRONIZAÇÃO E EXCLUSÕES
# ==============================================================================
@st.cache_data(ttl=60)
def carregar_dados_excel() -> Tuple[pd.DataFrame, List[str]]:
    """Carrega os dados diretamente da tabela simples."""
    if os.path.exists(ARQUIVO_EXCEL):
        try:
            df = pd.read_excel(ARQUIVO_EXCEL, sheet_name=NOME_ABA_GSHEETS, dtype=str, keep_default_na=False)
            df = padronizar_e_organizar_df(df)
            return df, list(df.columns)
        except Exception as err:
            st.error(f"Erro ao ler a planilha local: {err}")

    df_vazio = padronizar_e_organizar_df(pd.DataFrame(columns=COLUNAS_PADRAO))
    return df_vazio, COLUNAS_PADRAO


def salvar_no_excel(df: pd.DataFrame) -> None:
    """Salva a tabela de dados simples localmente e sincroniza na nuvem."""
    df_limpo = padronizar_e_organizar_df(df)

    try:
        with pd.ExcelWriter(ARQUIVO_EXCEL, engine="openpyxl") as writer:
            df_limpo.to_excel(writer, sheet_name=NOME_ABA_GSHEETS, index=False)
        aplicar_estilo_excel(ARQUIVO_EXCEL)
        carregar_dados_excel.clear()
    except Exception as err:
        st.error(f"Erro ao salvar arquivo Excel localmente: {err}")

    if conn is not None:
        try:
            conn.update(spreadsheet=GOOGLE_SHEET_URL, worksheet=NOME_ABA_GSHEETS, data=df_limpo)
            st.toast("☁️ Google Sheets sincronizado com sucesso!")
        except Exception as err:
            st.toast(f"⚠️ Salvo localmente. Erro na sincronização online: {err}")


def adicionar_e_salvar(codigo: str, descricao: str, setor: str) -> None:
    """Insere o dado recebido na célula do setor/coluna correspondente."""
    df, _ = carregar_dados_excel()
    coluna_alvo = descricao.strip()
    setor_limpo = setor.strip() if setor else "Não informado"
    codigo_limpo = str(codigo).strip()

    if coluna_alvo not in df.columns:
        df[coluna_alvo] = ""

    df = padronizar_e_organizar_df(df)
    mascara_setor = df[COLUNA_CHAVE].str.lower().eq(setor_limpo.lower())

    if mascara_setor.any():
        idx_linha = df[mascara_setor].index[0]
        df.at[idx_linha, coluna_alvo] = codigo_limpo
    else:
        nova_linha = {col: "" for col in df.columns}
        nova_linha[COLUNA_CHAVE] = setor_limpo
        nova_linha[coluna_alvo] = codigo_limpo
        df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)

    df = padronizar_e_organizar_df(df)
    salvar_no_excel(df)
    st.session_state.df_historico = df


def excluir_setor(setor_nome: str) -> None:
    """Exclui a linha inteira referente ao setor especificado."""
    df, _ = carregar_dados_excel()
    if df.empty or COLUNA_CHAVE not in df.columns:
        return

    mascara_manter = ~df[COLUNA_CHAVE].str.strip().str.lower().eq(setor_nome.strip().lower())
    df_filtrado = df[mascara_manter].copy()
    
    salvar_no_excel(df_filtrado)
    st.session_state.df_historico = df_filtrado


def excluir_patrimonio(setor_nome: str, coluna_patrimonio: str) -> None:
    """Limpa somente o valor do patrimônio específico dentro da linha do setor selecionado."""
    df, _ = carregar_dados_excel()
    if df.empty or COLUNA_CHAVE not in df.columns or coluna_patrimonio not in df.columns:
        return

    mascara_setor = df[COLUNA_CHAVE].str.strip().str.lower().eq(setor_nome.strip().lower())
    if mascara_setor.any():
        df.loc[mascara_setor, coluna_patrimonio] = ""
        salvar_no_excel(df)
        st.session_state.df_historico = df


def sincronizar_estrutura_menus() -> None:
    """Sincroniza os setores e colunas padrão com a planilha remota."""
    df, _ = carregar_dados_excel()

    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = ""

    for setor in SETORES_PADRAO:
        mascara_setor = df[COLUNA_CHAVE].str.lower().eq(setor.lower())
        if not mascara_setor.any():
            nova_linha = {col: "" for col in df.columns}
            nova_linha[COLUNA_CHAVE] = setor
            df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)

    df = padronizar_e_organizar_df(df)
    salvar_no_excel(df)
    st.session_state.df_historico = df

# ==============================================================================
# 6. PROCESSAMENTO E DECODIFICAÇÃO DE IMAGENS (OPENCV & ZXING)
# ==============================================================================
def processar_imagem(image_file: Any) -> Tuple[Optional[np.ndarray], List[Dict[str, str]]]:
    """Processa o upload da imagem e decodifica os códigos de barra."""
    try:
        import cv2
        import zxingcpp

        if hasattr(image_file, "getvalue"):
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
            if hasattr(barcode, "position") and barcode.position:
                try:
                    pos = barcode.position
                    if hasattr(pos, "top_left"):
                        pts_list = [
                            [int(pos.top_left.x), int(pos.top_left.y)],
                            [int(pos.top_right.x), int(pos.top_right.y)],
                            [int(pos.bottom_right.x), int(pos.bottom_right.y)],
                            [int(pos.bottom_left.x), int(pos.bottom_left.y)]
                        ]
                    else:
                        pts_list = [[int(getattr(pt, "x", pt[0])), int(getattr(pt, "y", pt[1]))] for pt in pos]

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
    except Exception as err:
        st.error(f"Erro durante o processamento da imagem: {err}")
        return None, []

# ==============================================================================
# 7. INTERFACE DO USUÁRIO (STREAMLIT)
# ==============================================================================
def renderizar_card_inventario(lista_urs: List[str], lista_ubs: List[str]) -> None:
    """Renderiza a seleção da unidade de saúde."""
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


def renderizar_sistema_inventario() -> None:
    """Renderiza os controles do leitor e a visualização simples dos dados."""
    df_inicial, _ = carregar_dados_excel()

    if "df_historico" not in st.session_state:
        st.session_state.df_historico = df_inicial

    if "saved_setor" not in st.session_state:
        st.session_state.saved_setor = ""

    if "saved_descricao" not in st.session_state:
        st.session_state.saved_descricao = ""

    st.title("📦 Sistema de Inventários - GTI-SESA")

    if st.button("🌐 Sincronizar Estrutura dos Menus com Google Sheets", type="secondary"):
        sincronizar_estrutura_menus()
        st.success("Setores e colunas sincronizados com sucesso na planilha online!")
        st.rerun()

    st.divider()

    unidade = st.session_state.get("unidade_selecionada", "")
    if unidade:
        st.subheader(f"🏥 Unidade: {unidade}")

    opcoes_setor = SETORES_PADRAO + ["➕ Outro Setor"]

    colunas_df_atuais = [
        col for col in st.session_state.df_historico.columns
        if col != COLUNA_CHAVE and col not in COLUNAS_OBSOLETAS
    ]

    opcoes_patrimonio = list(dict.fromkeys(colunas_df_atuais + [c for c in COLUNAS_PADRAO if c != COLUNA_CHAVE]))
    opcoes_patrimonio.append("➕ Outros Patrimônios")

    # Filtros e Parâmetros
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
        opcao_selecionada = st.selectbox("Tipo de patrimônio:", opcoes_patrimonio, key="opcao_selecionada_key")

    with col_desc3:
        if opcao_selecionada == "➕ Outros Patrimônios":
            descricao_final = st.text_input("Nome do Novo Patrimonio:", placeholder="Ex: Servidor", key="descricao_nova_key")
        else:
            descricao_final = opcao_selecionada
        st.session_state.saved_descricao = descricao_final

    st.divider()

    if not descricao_final or not setor_input.strip():
        st.warning("⚠️ Preencha o **Setor** e o **Tipo de patrimônio** para habilitar o leitor.")
    else:
        tab_unificada, tab_upload = st.tabs(["⚡ Câmera / Scanner USB", "📁 Upload de Imagem"])

        # Aba 1: Leitor Câmera / USB
        with tab_unificada:
            st.markdown(f"📍 Setor Ativo: **`{setor_input}`** | Coluna Destino: **`{descricao_final}`**")
            col_camera, col_usb = st.columns([1.2, 1])

            with col_camera:
                st.caption("Aponte a câmera para o código de barras.")
                html_scanner = """
                <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
                <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
                <style>
                    #reader { width: 100% !important; max-width: 100% !important; border-radius: 12px; overflow: hidden; border: 2px solid #1E293B; background-color: #000; }
                    #reader video { object-fit: cover !important; border-radius: 10px; }
                    #scan-status { text-align: center; margin-top: 8px; font-weight: bold; color: #1E293B; font-family: sans-serif; font-size: 14px; }
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
                    codigo_input = st.text_input(
                        "Código Lido / Bipado:", 
                        autocomplete="off", 
                        placeholder="Aguardando bipagem...", 
                        key="input_codigo_bip"
                    )
                    btn_adicionar = st.form_submit_button("Registrar Manualmente", type="primary", use_container_width=True)
                    if btn_adicionar and codigo_input.strip():
                        adicionar_e_salvar(codigo_input.strip(), descricao_final, setor_input)
                        st.success(f"✅ Código `{codigo_input.strip()}` registrado na coluna **'{descricao_final}'** | Setor **'{setor_input}'**")
                        st.rerun()

        # Aba 2: Upload de Imagem
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
                            adicionar_e_salvar(item["codigo"], descricao_final, setor_input)
                            st.write(f"**Código:** `{item['codigo']}` ➡️ Coluna: **{descricao_final}** | Setor: **{setor_input}**")
                        st.rerun()

    # Exibição da Tabela Simples e Estilizada no Streamlit
    st.divider()
    st.header("📊 Tabela de Patrimônios")
    df_atual, _ = carregar_dados_excel()

    if not df_atual.empty:
        # Aplicar estilo corporativo na exibição interativa
        df_styled = df_atual.style.set_properties(**{
            'font-family': 'Segoe UI, sans-serif',
            'font-size': '14px'
        }).set_table_styles([
            {'selector': 'th', 'props': [('background-color', '#1E293B'), ('color', '#FFFFFF'), ('font-weight', 'bold'), ('text-align', 'center')]},
            {'selector': 'td:first-child', 'props': [('font-weight', 'bold'), ('background-color', '#F1F5F9')]}
        ])

        st.dataframe(df_styled, use_container_width=True)
        
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            if st.button("🔄 Recarregar Dados", use_container_width=True):
                carregar_dados_excel.clear()
                st.rerun()
        with col_btn2:
            csv_data = df_atual.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Baixar Tabela (CSV)",
                data=csv_data,
                file_name="Tabela_Patrimonios_Sincronizada.csv",
                mime="text/csv",
                use_container_width=True
            )

        # Controles de Exclusão Otimizados
        with st.expander("🗑️ Gerenciador de Exclusão", expanded=False):
            st.markdown("Selecione o tipo de exclusão que deseja realizar na tabela:")
            
            lista_setores_existentes = [s for s in df_atual[COLUNA_CHAVE].tolist() if str(s).strip()]

            tab_excluir_setor, tab_excluir_patrimonio = st.tabs(["🗑️ Excluir Setor", "❌ Excluir Patrimônio"])

            # Aba: Exclusão do Setor Completo
            with tab_excluir_setor:
                if lista_setores_existentes:
                    setor_para_excluir = st.selectbox(
                        "Selecione o Setor para apagar inteiramente:", 
                        lista_setores_existentes, 
                        key="sb_excluir_setor"
                    )
                    st.caption("⚠️ Ao excluir o setor, **toda a linha** correspondente será removida da tabela.")
                    
                    if st.button(f"🔥 Confirmar Exclusão da Linha de '{setor_para_excluir}'", type="primary", key="btn_del_setor"):
                        excluir_setor(setor_para_excluir)
                        st.success(f"Linha referente ao setor **'{setor_para_excluir}'** foi excluída com sucesso!")
                        st.rerun()
                else:
                    st.info("Nenhum setor disponível para exclusão.")

            # Aba: Exclusão de Item/Patrimônio Específico (Filtrando apenas células preenchidas)
            with tab_excluir_patrimonio:
                if lista_setores_existentes:
                    c_del1, c_del2 = st.columns(2)
                    
                    with c_del1:
                        setor_patrimonio_del = st.selectbox(
                            "Selecione o Setor:", 
                            lista_setores_existentes, 
                            key="sb_setor_del_patrimonio"
                        )
                    
                    # Obter a linha do setor selecionado para filtrar quais colunas possuem valor salvo
                    mascara_setor_del = df_atual[COLUNA_CHAVE].str.strip().str.lower().eq(setor_patrimonio_del.strip().lower())
                    linha_setor_df = df_atual[mascara_setor_del]

                    colunas_com_dados: List[str] = []
                    valores_map: Dict[str, str] = {}
                    
                    if not linha_setor_df.empty:
                        linha_dados = linha_setor_df.iloc[0]
                        for col in df_atual.columns:
                            if col != COLUNA_CHAVE and col not in COLUNAS_OBSOLETAS:
                                val = str(linha_dados[col]).strip()
                                # Exibe no dropdown SOMENTE colunas que contêm dados salvos na célula (não vazia)
                                if val and val.lower() not in ["", "nan", "none", "null", "<na>"]:
                                    colunas_com_dados.append(col)
                                    valores_map[col] = val

                    with c_del2:
                        if colunas_com_dados:
                            coluna_patrimonio_del = st.selectbox(
                                "Selecione o Tipo de Patrimônio:", 
                                options=colunas_com_dados,
                                format_func=lambda c: f"{c} (Código: {valores_map.get(c, '')})",
                                key=f"sb_coluna_del_{setor_patrimonio_del}"
                            )
                        else:
                            coluna_patrimonio_del = None
                            st.info(f"ℹ️ Não há patrimônios registrados para o setor **'{setor_patrimonio_del}'** no momento.")

                    if coluna_patrimonio_del:
                        codigo_atual = valores_map.get(coluna_patrimonio_del, "")
                        st.caption(f"ℹ️ Somente o código `{codigo_atual}` na coluna **'{coluna_patrimonio_del}'** do setor **'{setor_patrimonio_del}'** será apagado.")

                        if st.button(f"🗑️ Apagar '{coluna_patrimonio_del}' em '{setor_patrimonio_del}'", type="secondary", key=f"btn_del_patrimonio_{setor_patrimonio_del}_{coluna_patrimonio_del}"):
                            excluir_patrimonio(setor_patrimonio_del, coluna_patrimonio_del)
                            st.success(f"O item **'{coluna_patrimonio_del}'** (Código: `{codigo_atual}`) do setor **'{setor_patrimonio_del}'** foi apagado com sucesso!")
                            st.rerun()
                else:
                    st.info("Nenhum setor disponível para exclusão.")