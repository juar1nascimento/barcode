import streamlit as st
import cv2
import numpy as np
from PIL import Image
import zxingcpp
import pandas as pd
import os
from streamlit_gsheets import GSheetsConnection

# ==========================================
# CONFIGURAÇÕES E CONSTANTES
# ==========================================
ARQUIVO_EXCEL = "Tabela_Patrimonios_UBS_Feu_Rosa.xlsx"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/12mNKTWLExRwZx3EKSB78oTScQk6ctGvi6eNKt5QyXEw/edit?usp=sharing"

# Colunas Padrão Fixas da Tabela (Ordem exata do formulário)
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
# FUNÇÕES DE MANIPULAÇÃO DO EXCEL E GOOGLE SHEETS
# ==========================================
def padronizar_e_organizar_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garante que as colunas padrão existam e fiquem nas primeiras posições,
    seguidas de forma ordenada por qualquer nova descrição criada.
    """
    # Garante que todas as colunas padrão existam
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = ""

    # Mantém COLUNAS_PADRAO no início e novas descrições ao final
    outras_colunas = [c for c in df.columns if c not in COLUNAS_PADRAO]
    ordem_final = COLUNAS_PADRAO + outras_colunas

    # Retorna o DataFrame reordenado, sem nulos e com tipos string
    return df[ordem_final].fillna("").astype(str)

def carregar_dados_excel() -> tuple[pd.DataFrame, list[str]]:
    """Carrega o DataFrame e força a padronização das colunas."""
    if os.path.exists(ARQUIVO_EXCEL):
        try:
            # Tenta ler a planilha
            df = pd.read_excel(ARQUIVO_EXCEL, sheet_name='Patrimônios', dtype=str, keep_default_na=False)
            
            # Se foi lido um formato antigo com linha de título mesclada, corrige
            if not df.empty and df.columns[0].startswith("Tabela de Patrimônios"):
                df = pd.read_excel(ARQUIVO_EXCEL, sheet_name='Patrimônios', header=1, dtype=str, keep_default_na=False)

            df = df.dropna(how='all')
            
            # Se a planilha não possuía o cabeçalho correto (como no print), renomeia/ajusta
            if len(df.columns) >= 4 and "Patrimônio PC" not in df.columns:
                novas_cols = list(df.columns)
                for i, col_std in enumerate(COLUNAS_PADRAO):
                    if i < len(novas_cols):
                        novas_cols[i] = col_std
                df.columns = novas_cols

            df = padronizar_e_organizar_df(df)
            return df, list(df.columns)
        except Exception as e:
            st.error(f"Erro ao carregar a planilha existente: {e}")
    
    # Se o arquivo não existir, retorna DataFrame limpo padronizado
    df_empty = pd.DataFrame(columns=COLUNAS_PADRAO)
    df_empty = padronizar_e_organizar_df(df_empty)
    return df_empty, COLUNAS_PADRAO

def salvar_no_excel(df: pd.DataFrame) -> None:
    """Salva no arquivo Excel local e sincroniza o cabeçalho limpo no Google Sheets."""
    df = padronizar_e_organizar_df(df)
    
    # 1. Salvamento Local em Excel
    try:
        with pd.ExcelWriter(ARQUIVO_EXCEL, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Patrimônios', index=False)
    except Exception as e:
        st.error(f"Erro ao salvar na planilha local: {e}")

    # 2. Sincronização direta no Google Sheets (Sobrevive limpando o cabeçalho na Linha 1)
    if conn is not None:
        try:
            conn.update(
                spreadsheet=GOOGLE_SHEET_URL,
                data=df
            )
            st.toast("☁️ Dados sincronizados no Google Sheets com sucesso!")
        except Exception as e:
            st.error(f"Falha na sincronização com Google Sheets: {e}")

def adicionar_e_salvar(codigo: str, descricao: str, setor: str) -> None:
    """Insere ou atualiza o código garantindo o alinhamento de colunas existentes e novas."""
    df, _ = carregar_dados_excel()
    
    coluna_alvo = descricao.strip()
    setor_limpo = setor.strip() if setor else "Não informado"
    codigo_limpo = str(codigo).strip()
    
    # Adiciona a nova descrição no cabeçalho se ainda não existir
    if coluna_alvo not in df.columns:
        df[coluna_alvo] = ""
    
    df = padronizar_e_organizar_df(df)
    
    # Busca a linha correspondente ao setor inserido
    df["Local / Setor"] = df["Local / Setor"].str.strip()
    mascara_setor = df["Local / Setor"].str.lower() == setor_limpo.lower()
    
    if mascara_setor.any():
        # Atualiza a célula correspondente
        idx = df[mascara_setor].index[0]
        df.at[idx, coluna_alvo] = codigo_limpo
    else:
        # Cria uma nova linha alinhando com TODAS as colunas cadastradas até agora
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