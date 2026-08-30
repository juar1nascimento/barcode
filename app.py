import streamlit as st
import cv2
import numpy as np
from PIL import Image
import zxingcpp
import pandas as pd
import os
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# ==========================================
# CONFIGURAÇÕES E CONSTANTES
# ==========================================
ARQUIVO_EXCEL = "Tabela_Patrimonios_UBS_Feu_Rosa.xlsx"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1yzNx6WcCrZbb-KvZCEpFYAuX025p-iy1/edit"

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
# FUNÇÕES DE MANIPULAÇÃO DO EXCEL E GOOGLE SHEETS
# ==========================================
def carregar_dados_excel() -> tuple[pd.DataFrame, list[str]]:
    """Carrega o DataFrame mantendo a estrutura exata do cabeçalho da planilha."""
    if os.path.exists(ARQUIVO_EXCEL):
        try:
            # Lê pulando a linha 0 (título da tabela) para pegar os nomes reais das colunas
            df = pd.read_excel(ARQUIVO_EXCEL, header=1)
            # Remove linhas completamente vazias
            df = df.dropna(how='all')
            colunas = df.columns.tolist()
            return df, colunas
        except Exception as e:
            st.error(f"Erro ao carregar a planilha existente: {e}")
    
    # Estrutura padrão baseada no arquivo fornecido caso não exista
    colunas_padrao = ["Local / Setor", "Patrimônio PC", "Patrimônio Tela", "Patrimônio Nobreak"]
    return pd.DataFrame(columns=colunas_padrao), colunas_padrao

def salvar_no_excel(df: pd.DataFrame) -> None:
    """Salva no arquivo Excel local e sincroniza com o Google Sheets."""
    # 1. Salvamento Local (Excel)
    try:
        with pd.ExcelWriter(ARQUIVO_EXCEL, engine='openpyxl') as writer:
            df_titulo = pd.DataFrame([["Tabela de Patrimônios UBS Feu Rosa"] + [""] * (len(df.columns) - 1)])
            df_titulo.to_excel(writer, sheet_name='Patrimônios', header=False, index=False, startrow=0)
            df.to_excel(writer, sheet_name='Patrimônios', header=True, index=False, startrow=1)
    except Exception as e:
        st.error(f"Erro ao salvar na planilha local: {e}")

    # 2. Sincronização em Tempo Real com o Google Sheets
    if conn is not None:
        try:
            # Monta o DataFrame preservando a linha de título original
            df_titulo = pd.DataFrame([["Tabela de Patrimônios UBS Feu Rosa"] + [""] * (len(df.columns) - 1)], columns=df.columns)
            df_sync = pd.concat([df_titulo, df], ignore_index=True)
            
            # Atualiza no Google Sheets
            conn.update(
                spreadsheet=GOOGLE_SHEET_URL,
                data=df_sync
            )
        except Exception as e:
            st.warning(f"Sincronização com Google Sheets pendente (Configure as credenciais): {e}")

def adicionar_e_salvar(codigo: str, descricao: str, setor: str) -> None:
    """Insere o código na coluna correspondente na sequência da tabela."""
    df, colunas_existentes = carregar_dados_excel()
    
    coluna_alvo = descricao.strip()
    
    if coluna_alvo not in df.columns:
        df[coluna_alvo] = np.nan
    
    nova_linha = {col: "" for col in df.columns}
    
    if "Local / Setor" in df.columns and setor:
        nova_linha["Local / Setor"] = setor
    else:
        nova_linha["Local / Setor"] = "Não informado"
        
    nova_linha[coluna_alvo] = str(codigo).strip()
    
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    df = df.fillna("")
    
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
    setor_input = st.text_input("Local / Setor (Opcional):", placeholder="Ex: Consultório 1, Recepção...")

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

if not descricao_final:
    st.warning("⚠️ Por favor, selecione ou informe a descrição antes de realizar a leitura.")
else:
    tab_manual, tab_webcam, tab_upload = st.tabs([
        "⌨️ Digitação / Leitor USB", 
        "📷 Captura via Webcam", 
        "📁 Upload de Imagem"
    ])

    with tab_manual:
        st.markdown(f"Registrando na coluna: **`{descricao_final}`**")
        with st.form(key="form_manual", clear_on_submit=True):
            codigo_input = st.text_input("Digite ou bipe o código de barras:", autocomplete="off")
            btn_adicionar = st.form_submit_button("Registrar na Tabela")

            if btn_adicionar and codigo_input.strip():
                adicionar_e_salvar(codigo_input.strip(), descricao_final, setor_input)
                st.success(f"✅ Código `{codigo_input.strip()}` inserido na coluna **'{descricao_final}'** no final da planilha!")

    with tab_webcam:
        st.markdown(f"Registrando na coluna: **`{descricao_final}`**")
        camera_image = st.camera_input("Tire uma foto focada no código de barras")

        if camera_image:
            img_processada, codigos_encontrados = processar_imagem(camera_image)
            
            col_img1, col_img2 = st.columns(2)
            with col_img1:
                st.image(img_processada, caption="Imagem Processada", use_column_width=True)
            
            with col_img2:
                if codigos_encontrados:
                    st.success(f"{len(codigos_encontrados)} código(s) detectado(s)!")
                    for item in codigos_encontrados:
                        adicionar_e_salvar(item['codigo'], descricao_final, setor_input)
                        st.write(f"**Código:** `{item['codigo']}` ➡️ Coluna: **{descricao_final}**")
                else:
                    st.warning("Nenhum código legível encontrado.")

    with tab_upload:
        st.markdown(f"Registrando na coluna: **`{descricao_final}`**")
        uploaded_file = st.file_uploader("Escolha uma imagem contendo o código", type=["jpg", "png", "jpeg"])

        if uploaded_file is not None:
            img_processada, codigos_encontrados = processar_imagem(uploaded_file)
            
            col_img1, col_img2 = st.columns(2)
            with col_img1:
                st.image(img_processada, caption="Imagem Processada", use_column_width=True)
                
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
st.header(f"📊 Tabela de Patrimônios Atualizada em Tempo Real")

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