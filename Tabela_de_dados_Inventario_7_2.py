import os
import re
from typing import Optional, Tuple, List, Any
import pandas as pd
import streamlit as st

# ==============================================================================
# CONFIGURAÇÕES E CONSTANTES DE DADOS
# ==============================================================================
ARQUIVO_EXCEL: str = "Tabela_Patrimonios_UBS_Feu_Rosa.xlsx"
GOOGLE_SHEET_URL: str = "https://docs.google.com/spreadsheets/d/12mNKTWLExRwZx3EKSB78oTScQk6ctGvi6eNKt5QyXEw/edit?usp=sharing"

COLUNA_CHAVE: str = "Local / Setor"
SUFIXO_PATRIMONIO: str = " - Nº de Patrimônio"

COLUNAS_PADRAO: List[str] = [
    COLUNA_CHAVE,
    f"CPU{SUFIXO_PATRIMONIO}",
    f"Monitores{SUFIXO_PATRIMONIO}",
    f"Nobreak{SUFIXO_PATRIMONIO}",
    f"Teclado{SUFIXO_PATRIMONIO}",
    f"Mouse{SUFIXO_PATRIMONIO}",
    f"Impressora{SUFIXO_PATRIMONIO}"
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

LISTA_URS_PADRAO: List[str] = [
    "Selecione uma URS...", "URS Feu Rosa", "URS Jacaraípe", 
    "URS Novo Horizonte", "URS Serra Dourada"
]

LISTA_UBS_PADRAO: List[str] = [
    "Selecione uma UBS...", "UBS Planalto Serrano", "UBS Bairro das Laranjeiras", 
    "UBS Nova Carapina", "UBS Vila Nova de Colares", "UBS Porto Canoa"
]

# ==============================================================================
# FUNÇÕES AUXILIARES DE FORMATAÇÃO E ARTICULAÇÃO GRAMATICAL
# ==============================================================================
def extrair_nome_base(nome: str) -> str:
    limpo = str(nome).strip()
    limpo = re.sub(r'^\s*Fabricante\s+(da|do|dos|das|de)\s+', '', limpo, flags=re.IGNORECASE)
    limpo = re.sub(r'^\s*Fabricante\s+', '', limpo, flags=re.IGNORECASE)
    limpo = re.sub(r'\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$', '', limpo, flags=re.IGNORECASE)
    return limpo.strip()

def formatar_nome_patrimonio(nome_patrimonio: str) -> str:
    base = extrair_nome_base(nome_patrimonio)
    if not base or base == COLUNA_CHAVE:
        return nome_patrimonio.strip()
    return f"{base}{SUFIXO_PATRIMONIO}"

def formatar_nome_fabricante(nome_patrimonio: str) -> str:
    base = extrair_nome_base(nome_patrimonio)
    if not base or base == COLUNA_CHAVE:
        return ""

    base_lower = base.lower()
    fem_singular = ["cpu", "impressora", "webcam", "tela", "câmera", "camera", "placa", "mesa", "televisão", "tv"]
    fem_plural = ["impressoras", "telas", "cameras", "câmeras", "placas"]
    masc_plural = ["monitores", "teclados", "mouses", "nobreaks", "servidores", "racks", "estabilizadores"]

    if any(base_lower.startswith(w) for w in fem_singular):
        preposicao = "da"
    elif any(base_lower.startswith(w) for w in fem_plural):
        preposicao = "das"
    elif any(base_lower.startswith(w) for w in masc_plural):
        preposicao = "dos"
    else:
        preposicao = "do"

    return f"Fabricante {preposicao} {base}"

def sanitizar_nome_aba(nome_unidade: str) -> str:
    if not nome_unidade or not str(nome_unidade).strip():
        return "Geral"
    return re.sub(r'[\\/*?:\[\]]', '_', str(nome_unidade).strip())[:31]

# ==============================================================================
# CAMADA DE CONEXÃO REMOTA (GOOGLE SHEETS)
# ==============================================================================
def obter_conexao_gsheets() -> Optional[Any]:
    try:
        from streamlit_gsheets import GSheetsConnection
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception as err:
        print(f"[AVISO GSHEETS]: {err}")
        return None

def sincronizar_google_sheets(df: pd.DataFrame, nome_aba: str) -> bool:
    try:
        conn = obter_conexao_gsheets()
        if conn is not None:
            conn.update(spreadsheet=GOOGLE_SHEET_URL, worksheet=nome_aba, data=df)
            st.toast(f"☁️ Aba '{nome_aba}' sincronizada no Google Sheets!")
            return True
    except Exception as err:
        print(f"[ERRO GSHEETS]: {err}")
    return False

# ==============================================================================
# REGRAS DE NEGÓCIO, MIGRAÇÃO DE DADOS E ORGANIZAÇÃO DA TABELA
# ==============================================================================
def padronizar_e_organizar_df(df: pd.DataFrame) -> pd.DataFrame:
    colunas_invisiveis = [
        c for c in df.columns 
        if c in COLUNAS_OBSOLETAS or str(c).startswith("➕") or "Unnamed" in str(c)
    ]
    if colunas_invisiveis:
        df = df.drop(columns=colunas_invisiveis, errors="ignore")

    renomear_map = {}
    for col in df.columns:
        if col != COLUNA_CHAVE:
            if str(col).startswith("Fabricante "):
                novo_fab = formatar_nome_fabricante(col)
                if novo_fab and novo_fab != col:
                    renomear_map[col] = novo_fab
            else:
                novo_pat = formatar_nome_patrimonio(col)
                if novo_pat != col:
                    renomear_map[col] = novo_pat

    if renomear_map:
        df_novo = pd.DataFrame()
        for c in df.columns:
            target_c = renomear_map.get(c, c)
            if target_c not in df_novo.columns:
                df_novo[target_c] = df[c].astype(str)
            else:
                val_existente = df_novo[target_c].replace(["nan", "None", "<NA>"], "").astype(str)
                val_novo = df[c].replace(["nan", "None", "<NA>"], "").astype(str)
                df_novo[target_c] = val_existente.combine(val_novo, lambda x, y: y if y.strip() != "" else x)
        df = df_novo

    if COLUNA_CHAVE not in df.columns:
        df.insert(0, COLUNA_CHAVE, "")

    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = ""

    ordem_colunas = [COLUNA_CHAVE]
    todas_colunas = [str(c).strip() for c in df.columns]

    for col in todas_colunas:
        if col == COLUNA_CHAVE or str(col).startswith("Fabricante "):
            continue
        if col not in ordem_colunas:
            ordem_colunas.append(col)
        
        col_fab = formatar_nome_fabricante(col)
        if col_fab in todas_colunas and col_fab not in ordem_colunas:
            ordem_colunas.append(col_fab)

    for col in todas_colunas:
        if str(col).startswith("Fabricante ") and col not in ordem_colunas:
            ordem_colunas.append(col)

    df_processado = df.reindex(columns=ordem_colunas).fillna("").astype(str)
    df_processado[COLUNA_CHAVE] = df_processado[COLUNA_CHAVE].str.strip()
    return df_processado

def aplicar_estilo_excel(caminho_arquivo: str, nome_aba: str) -> None:
    if not os.path.exists(caminho_arquivo): return
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.load_workbook(caminho_arquivo)
        if nome_aba not in wb.sheetnames: return
        ws = wb[nome_aba]

        header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        row_even_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        row_odd_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        col_chave_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        thin_border = Side(border_style="thin", color="CBD5E1")
        border_box = Border(left=thin_border, right=thin_border, top=thin_border, bottom=thin_border)
        align_center, align_left = Alignment(horizontal="center", vertical="center"), Alignment(horizontal="left", vertical="center")
        font_data, font_sector = Font(name="Segoe UI", size=10, color="0F172A"), Font(name="Segoe UI", size=10, bold=True, color="0F172A")

        ws.row_dimensions[1].height = 30
        for cell in ws[1]:
            cell.fill, cell.font, cell.alignment, cell.border = header_fill, header_font, align_center, border_box

        for r in range(2, ws.max_row + 1):
            ws.row_dimensions[r].height = 22
            fill = row_odd_fill if r % 2 == 1 else row_even_fill
            for c in range(1, ws.max_column + 1):
                cell = ws.cell(row=r, column=c)
                cell.border, cell.number_format = border_box, "@"
                if c == 1:
                    cell.fill, cell.font, cell.alignment = col_chave_fill, font_sector, align_left
                else:
                    cell.fill, cell.font, cell.alignment = fill, font_data, align_center

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 20)

        wb.save(caminho_arquivo)
    except Exception as e:
        print(f"[AVISO EXCEL]: {e}")

# ==============================================================================
# CAMADA DE PERSISTÊNCIA E CRUD
# ==============================================================================
@st.cache_data(ttl=60)
def carregar_dados_excel(unidade_nome: str = "Geral") -> Tuple[pd.DataFrame, List[str]]:
    nome_aba = sanitizar_nome_aba(unidade_nome)
    
    if os.path.exists(ARQUIVO_EXCEL):
        try:
            xls = pd.ExcelFile(ARQUIVO_EXCEL)
            df = pd.read_excel(xls, sheet_name=nome_aba, dtype=str, keep_default_na=False) if nome_aba in xls.sheet_names else pd.DataFrame(columns=COLUNAS_PADRAO)
        except Exception: df = pd.DataFrame(columns=COLUNAS_PADRAO)
    else: df = pd.DataFrame(columns=COLUNAS_PADRAO)

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
        salvar_no_excel(df, unidade_nome=nome_aba)

    return df, list(df.columns)

def salvar_no_excel(df: pd.DataFrame, unidade_nome: str = "Geral") -> bool:
    nome_aba = sanitizar_nome_aba(unidade_nome)
    df_limpo = padronizar_e_organizar_df(df)
    sucesso_local = False

    try:
        dict_abas = {}
        if os.path.exists(ARQUIVO_EXCEL):
            try:
                xls = pd.ExcelFile(ARQUIVO_EXCEL)
                for sheet in xls.sheet_names:
                    if sheet != nome_aba:
                        dict_abas[sheet] = pd.read_excel(xls, sheet_name=sheet, dtype=str, keep_default_na=False)
            except Exception:
                pass
        
        dict_abas[nome_aba] = df_limpo

        with pd.ExcelWriter(ARQUIVO_EXCEL, engine="openpyxl") as writer:
            for sheet, data in dict_abas.items():
                data.to_excel(writer, sheet_name=sheet, index=False)

        aplicar_estilo_excel(ARQUIVO_EXCEL, nome_aba)
        carregar_dados_excel.clear()
        sucesso_local = True
    except Exception as err:
        st.error(f"❌ Erro ao salvar localmente: {err}")

    sincronizar_google_sheets(df_limpo, nome_aba)
    return sucesso_local

def excluir_setor(setor_nome: str, unidade_nome: str) -> None:
    df, _ = carregar_dados_excel(unidade_nome)
    if df.empty or COLUNA_CHAVE not in df.columns: return
    df_filtrado = df[~df[COLUNA_CHAVE].str.strip().str.lower().eq(setor_nome.strip().lower())].copy()
    salvar_no_excel(df_filtrado, unidade_nome)
    st.session_state.df_historico = df_filtrado

def excluir_patrimonio(setor_nome: str, coluna_patrimonio: str, unidade_nome: str) -> None:
    df, _ = carregar_dados_excel(unidade_nome)
    if df.empty or COLUNA_CHAVE not in df.columns or coluna_patrimonio not in df.columns: return
    mascara_setor = df[COLUNA_CHAVE].str.strip().str.lower().eq(setor_nome.strip().lower())
    if mascara_setor.any():
        df.loc[mascara_setor, coluna_patrimonio] = ""
        col_fab = formatar_nome_fabricante(coluna_patrimonio)
        if col_fab in df.columns:
            df.loc[mascara_setor, col_fab] = ""
        salvar_no_excel(df, unidade_nome)
        st.session_state.df_historico = df