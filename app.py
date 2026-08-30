import streamlit as st
import cv2
import numpy as np
from PIL import Image
import zxingcpp
import pandas as pd
import os
from streamlit_gsheets import GSheetsConnection
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ==========================================
# CONFIGURAÇÕES E CONSTANTES
# ==========================================
ARQUIVO_EXCEL = "Tabela_Patrimonios_UBS_Feu_Rosa.xlsx"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/12mNKTWLExRwZx3EKSB78oTScQk6ctGvi6eNKt5QyXEw/edit?usp=sharing"

# Cabeçalho Fixo e Obrigatório (Garante a estrutura exata)
COLUNAS_PADRAO = ["Local / Setor", "Patrimônio PC", "Patrimônio Tela", "Patrimônio Nobreak"]

st.set_page_config(
    page_title="Leitor de Código de Barras - UBS Feu Rosa",
    page_icon="📦",
    layout="wide"
)

# Inicializa conexão com o Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception:
    conn = None

# ==========================================
# FUNÇÕES DE ESTILIZAÇÃO E MANIPULAÇÃO
# ==========================================
def padronizar_e_organizar_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garante que os nomes das colunas estejam limpos, preserva o cabeçalho fixo 
    e alinha colunas criadas dinamicamente sem desorganizar a estrutura.
    """
    if df is None or df.empty:
        df = pd.DataFrame(columns=COLUNAS_PADRAO)
        
    # Limpa espaços extras nos nomes das colunas para evitar duplicações por erro de digitação
    df.columns = [str(c).strip() for c in df.columns]

    # Garante que as colunas padrão sempre existam
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = ""

    # Mantém COLUNAS_PADRAO no início e joga novas colunas adicionadas para o final
    outras_colunas = [c for c in df.columns if c not in COLUNAS_PADRAO]
    ordem_final = COLUNAS_PADRAO + outras_colunas

    return df[ordem_final].fillna("").astype(str)

def aplicar_estilo_excel(caminho_arquivo: str) -> None:
    """Aplica design profissional no arquivo Excel local preservando e estilizando o cabeçalho."""
    wb = openpyxl.load_workbook(caminho_arquivo)
    
    if 'Patrimônios' in wb.sheetnames:
        ws = wb['Patrimônios']
    else:
        ws = wb.active

    # Definindo Estilos Visuais
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid") # Azul corporativo
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    
    row_fill_even = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
    row_fill_odd = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")

    # 1. Estilizar Cabeçalho (Linha 1)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = thin_border
    ws.row_dimensions[1].height = 28

    # 2. Estilizar Linhas de Dados (Linha 2 em diante)
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

    # 3. Ajustar Largura das Colunas Dinamicamente
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 18)

    wb.save(caminho_arquivo)

def carregar_dados_excel() -> tuple[pd.DataFrame, list[str]]:
    """Carrega o DataFrame e força a padronização das colunas."""
    if os.path.exists(ARQUIVO_EXCEL):
        try:
            df = pd.read_excel(ARQUIVO_EXCEL, sheet_name='Patrimônios', dtype=str, keep_default_na=False)
            
            # Caso a planilha tenha um título na primeira linha, pula para a linha correta
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
    """Salva no arquivo Excel local com estilos e sincroniza no Google Sheets sem corromper o cabeçalho."""
    df = padronizar_e_organizar_df(df)
    
    # 1. Salvamento Local em Excel com Estilização
    try:
        with pd.ExcelWriter(ARQUIVO_EXCEL, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Patrimônios', index=False)
        aplicar_estilo_excel(ARQUIVO_EXCEL)
    except Exception as e:
        st.error(f"Erro ao salvar e formatar a planilha local: {e}")

    # 2. Sincronização direta no Google Sheets (Preservando Estrutura e Cabeçalho)
    if conn is not None:
        try:
            # Envia o DataFrame padronizado com cabeçalho limpo na primeira linha
            conn.update(
                spreadsheet=GOOGLE_SHEET_URL,
                data=df
            )
            st.toast("☁️ Dados e cabeçalho sincronizados com sucesso no Google Sheets!")
        except Exception as e:
            st.error(f"Falha na sincronização com Google Sheets: {e}")

def adicionar_e_salvar(codigo: str, descricao: str, setor: str) -> None:
    """Insere ou atualiza o código garantindo a preservação das colunas fixas e novas."""
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
    """Decodifica os códigos de barras a partir de imagem usando zxing-cpp."""
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
st.title("📦 Sistema de Controle de Patrimônio - UBS Feu Rosa")
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