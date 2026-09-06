import os
from typing import Optional, Tuple, List, Any
import pandas as pd
import streamlit as st

# ==============================================================================
# CONFIGURAÇÕES E CONSTANTES DE DADOS
# ==============================================================================
ARQUIVO_EXCEL: str = "Tabela_Patrimonios_UBS_Feu_Rosa.xlsx"
GOOGLE_SHEET_URL: str = "https://docs.google.com/spreadsheets/d/12mNKTWLExRwZx3EKSB78oTScQk6ctGvi6eNKt5QyXEw/edit?usp=sharing"
NOME_ABA_GSHEETS: str = "Patrimônios"

COLUNA_CHAVE: str = "Local / Setor"

COLUNAS_PADRAO: List[str] = [
    COLUNA_CHAVE, "CPU", "Monitores", "Nobreak", "Teclado", "Mouse", "Impressora"
]

COLUNAS_OBSOLETAS: List[str] = [
    "Patrimônio PC", "Patrimônio Tela", "Patrimônio Nobreak", 
    "➕ Outra descrição (Criar nova coluna ao final)", "cameras"
]

SETORES_PADRAO: List[str] = [
    "Consultório", "Gerência", "Administração", "Farmácia",
    "Almoxarifado", "Sala de Preparo", "Sala dos Agentes de Saúde",
    "Sala de Curativo", "Recepção", "Sala de Vacina"
]

# ==============================================================================
# CAMADA DE CONEXÃO REMOTA (GOOGLE SHEETS)
# ==============================================================================
@st.cache_resource
def obter_conexao_gsheets() -> Optional[Any]:
    """Estabelece conexão com o Google Sheets usando a lib streamlit-gsheets."""
    try:
        from streamlit_gsheets import GSheetsConnection
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception as err:
        st.caption(f"⚠️ Módulo GSheetsConnection indisponível: {err}")
        return None

conn = obter_conexao_gsheets()

# ==============================================================================
# REGRAS DE NEGÓCIO E TRATAMENTO DE DADOS
# ==============================================================================
def padronizar_e_organizar_df(df: pd.DataFrame) -> pd.DataFrame:
    """Higieniza o DataFrame removendo colunas obsoletas e garantindo a estrutura padrão."""
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
    """Aplica formatação visual profissional à planilha Excel usando OpenPyXL."""
    if not os.path.exists(caminho_arquivo):
        return
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.load_workbook(caminho_arquivo)
        ws = wb[NOME_ABA_GSHEETS] if NOME_ABA_GSHEETS in wb.sheetnames else wb.active

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

        ws.row_dimensions[1].height = 28
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align_center
            cell.border = border_box

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

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 5, 16)

        wb.save(caminho_arquivo)
    except Exception as e:
        st.warning(f"Aviso de formatação no Excel local: {e}")

# ==============================================================================
# CAMADA DE PERSISTÊNCIA E CRUD
# ==============================================================================
@st.cache_data(ttl=60)
def carregar_dados_excel() -> Tuple[pd.DataFrame, List[str]]:
    """Carrega, sincroniza e estrutura a base de dados."""
    if os.path.exists(ARQUIVO_EXCEL):
        try:
            df = pd.read_excel(ARQUIVO_EXCEL, sheet_name=NOME_ABA_GSHEETS, dtype=str, keep_default_na=False)
        except Exception:
            df = pd.DataFrame(columns=COLUNAS_PADRAO)
    else:
        df = pd.DataFrame(columns=COLUNAS_PADRAO)

    df = padronizar_e_organizar_df(df)
    
    houve_alteracao = False
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = ""
            houve_alteracao = True

    for setor in SETORES_PADRAO:
        if not df[COLUNA_CHAVE].str.lower().eq(setor.lower()).any():
            nova_linha = {col: "" for col in df.columns}
            nova_linha[COLUNA_CHAVE] = setor
            df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
            houve_alteracao = True

    df = padronizar_e_organizar_df(df)
    if houve_alteracao or not os.path.exists(ARQUIVO_EXCEL):
        salvar_no_excel(df)

    return df, list(df.columns)

def salvar_no_excel(df: pd.DataFrame) -> None:
    """Persiste os dados em arquivo local Excel e tenta sincronizar com Google Sheets."""
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
    """Adiciona ou atualiza um patrimônio vinculado a um setor."""
    df, _ = carregar_dados_excel()
    coluna_alvo = descricao.strip()
    setor_limpo = setor.strip() if setor else "Não informado"
    codigo_limpo = str(codigo).strip()

    if coluna_alvo not in df.columns:
        df[coluna_alvo] = ""

    df = padronizar_e_organizar_df(df)
    mascara_setor = df[COLUNA_CHAVE].str.lower().eq(setor_limpo.lower())

    if mascara_setor.any():
        df.at[df[mascara_setor].index[0], coluna_alvo] = codigo_limpo
    else:
        nova_linha = {col: "" for col in df.columns}
        nova_linha[COLUNA_CHAVE] = setor_limpo
        nova_linha[coluna_alvo] = codigo_limpo
        df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)

    df = padronizar_e_organizar_df(df)
    salvar_no_excel(df)
    st.session_state.df_historico = df

def excluir_setor(setor_nome: str) -> None:
    """Remove um setor inteiro (linha) da tabela."""
    df, _ = carregar_dados_excel()
    if df.empty or COLUNA_CHAVE not in df.columns:
        return
    mascara_manter = ~df[COLUNA_CHAVE].str.strip().str.lower().eq(setor_nome.strip().lower())
    df_filtrado = df[mascara_manter].copy()
    salvar_no_excel(df_filtrado)
    st.session_state.df_historico = df_filtrado

def excluir_patrimonio(setor_nome: str, coluna_patrimonio: str) -> None:
    """Limpa a célula do patrimônio específico em um determinado setor."""
    df, _ = carregar_dados_excel()
    if df.empty or COLUNA_CHAVE not in df.columns or coluna_patrimonio not in df.columns:
        return
    mascara_setor = df[COLUNA_CHAVE].str.strip().str.lower().eq(setor_nome.strip().lower())
    if mascara_setor.any():
        df.loc[mascara_setor, coluna_patrimonio] = ""
        salvar_no_excel(df)
        st.session_state.df_historico = df