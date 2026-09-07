import os
import re
import pandas as pd
import numpy as np
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from typing import Optional, Tuple, List, Dict, Any

# Configurações globais e constantes
ARQUIVO_EXCEL = "inventario_dados.xlsx"
COLUNA_CHAVE = "Local / Setor"
COLUNAS_OBSOLETAS = ["Data_Hora", "Usuario", "Status", "Setor"]
COLUNAS_PADRAO = [
    "Computador - Nº de Patrimônio", "Fabricante Computador",
    "Monitor - Nº de Patrimônio", "Fabricante Monitor",
    "Impressora - Nº de Patrimônio", "Fabricante Impressora"
]
SETORES_PADRAO = ["Recepção", "Triagem", "Farmácia", "Consultório", "Almoxarifado"]
LISTA_URS_PADRAO = ["URS I", "URS II", "URS III"]
LISTA_UBS_PADRAO = ["UBS Central", "UBS Jardim", "UBS Vila Nova"]

def formatar_nome_patrimonio(patrimonio: str) -> str:
    p_limpo = patrimonio.strip()
    if not re.search(r'-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$', p_limpo, flags=re.IGNORECASE):
        return f"{p_limpo} - Nº de Patrimônio"
    return p_limpo

def formatar_nome_fabricante(patrimonio: str) -> str:
    p_limpo = re.sub(r'\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$', '', patrimonio.strip(), flags=re.IGNORECASE)
    return f"Fabricante {p_limpo}"

# ==============================================================================
# CONEXÃO GOOGLE SHEETS COM SUPORTE A [connections.gsheets]
# ==============================================================================
def conectar_google_sheets():
    """Conecta ao Google Sheets buscando os dados dentro de [connections.gsheets]."""
    try:
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            sec_gsheets = st.secrets["connections"]["gsheets"]
        elif "gcp_service_account" in st.secrets:
            sec_gsheets = st.secrets["gcp_service_account"]
        else:
            return None

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets", 
            "https://www.googleapis.com/auth/drive"
        ]
        
        creds_dict = {
            "type": sec_gsheets.get("type", "service_account"),
            "project_id": sec_gsheets.get("project_id"),
            "private_key_id": sec_gsheets.get("private_key_id"),
            "private_key": sec_gsheets.get("private_key"),
            "client_email": sec_gsheets.get("client_email"),
            "client_id": sec_gsheets.get("client_id"),
            "auth_uri": sec_gsheets.get("auth_uri"),
            "token_uri": sec_gsheets.get("token_uri"),
            "auth_provider_x509_cert_url": sec_gsheets.get("auth_provider_x509_cert_url"),
            "client_x509_cert_url": sec_gsheets.get("client_x509_cert_url")
        }

        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        sheet_url = sec_gsheets.get("spreadsheet") or st.secrets.get("spreadsheet_url")
        if sheet_url:
            return client.open_by_url(sheet_url)

    except Exception as e:
        st.warning(f"Não foi possível conectar ao Google Sheets: {e}")
    return None

def expurgar_e_normalizar_setores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Regra estrita: consolida a seleção do menu suspenso do site exclusivamente
    na coluna 'Local / Setor' e deleta qualquer ocorrência da antiga coluna 'Setor'.
    """
    df = df.copy()
    
    # 1. Se existir a coluna antiga 'Setor', transfere seus dados para 'Local / Setor'
    if "Setor" in df.columns:
        if COLUNA_CHAVE in df.columns:
            df[COLUNA_CHAVE] = df[COLUNA_CHAVE].replace("", np.nan).fillna(df["Setor"]).fillna("")
        else:
            df[COLUNA_CHAVE] = df["Setor"]
        df = df.drop(columns=["Setor"])

    # 2. Assegura que 'Local / Setor' exista na posição inicial
    if COLUNA_CHAVE not in df.columns:
        df.insert(0, COLUNA_CHAVE, "")

    # 3. Elimina qualquer coluna obsoleta da tabela
    cols_para_remover = [c for c in COLUNAS_OBSOLETAS if c in df.columns]
    if cols_para_remover:
        df = df.drop(columns=cols_para_remover)

    # 4. Ordena para colocar 'Local / Setor' na primeira coluna (Coluna A)
    colunas_finais = [COLUNA_CHAVE] + [c for c in df.columns if c != COLUNA_CHAVE]
    return df[colunas_finais]

def remover_coluna_setor_da_planilha(aba: gspread.Worksheet):
    """
    Verifica no Google Sheets se a coluna A é 'Setor' e exclui fisicamente a coluna da aba.
    """
    try:
        primeira_linha = aba.row_values(1)
        if primeira_linha and primeira_linha[0].strip().lower() == "setor":
            aba.delete_columns(1)  # Apaga fisicamente a coluna A no Google Sheets
    except Exception:
        pass

def aplicar_estilizacao_sheets(aba: gspread.Worksheet, total_linhas: int, total_colunas: int):
    """
    Aplica a formatação visual e alinhamento na aba do Google Sheets.
    """
    try:
        aba.freeze(rows=1)

        # Estilo do Cabeçalho (Azul Escuro com texto Branco)
        aba.format(f"A1:{gspread.utils.rowcol_to_a1(1, total_colunas)}", {
            "backgroundColor": {"red": 0.12, "green": 0.30, "blue": 0.47},
            "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True, "fontSize": 10},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE"
        })

        if total_linhas > 1:
            intervalo_dados = f"A2:{gspread.utils.rowcol_to_a1(total_linhas, total_colunas)}"
            aba.format(intervalo_dados, {
                "textFormat": {"fontSize": 9},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE"
            })
    except Exception:
        pass

@st.cache_data(ttl=2)
def carregar_dados_excel(unidade: str) -> Tuple[pd.DataFrame, str]:
    """
    Carrega dados do Google Sheets aplicando a regra de leitura em 'Local / Setor'.
    """
    planilha = conectar_google_sheets()
    nome_aba = re.sub(r'[^a-zA-Z0-9_ ]', '_', unidade)[:30].strip()
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"

    if planilha:
        try:
            aba = planilha.worksheet(nome_aba)
            
            # Remove fisicamente a coluna 'Setor' do Sheets se ela ainda existir lá
            remover_coluna_setor_da_planilha(aba)

            valores = aba.get_all_values()
            if valores and len(valores) > 1:
                df = pd.DataFrame(valores[1:], columns=valores[0])
                df = df.fillna("").astype(str)
                df = expurgar_e_normalizar_setores(df)
                return df, f"Google Sheets ({nome_aba})"
            elif valores and len(valores) == 1:
                df = pd.DataFrame(columns=valores[0])
                df = expurgar_e_normalizar_setores(df)
                return df, f"Google Sheets ({nome_aba})"
            else:
                return pd.DataFrame(columns=[COLUNA_CHAVE] + COLUNAS_PADRAO), f"Google Sheets ({nome_aba})"
        except gspread.exceptions.WorksheetNotFound:
            pass
        except Exception as e:
            st.error(f"Erro ao ler do Google Sheets: {e}")

    # Fallback arquivo local
    if os.path.exists(nome_arquivo_local):
        try:
            df = pd.read_excel(nome_arquivo_local, dtype=str)
            df = df.fillna("")
            df = expurgar_e_normalizar_setores(df)
            return df, nome_arquivo_local
        except Exception:
            pass

    return pd.DataFrame(columns=[COLUNA_CHAVE] + COLUNAS_PADRAO), nome_arquivo_local

def adicionar_ou_atualizar_registro(unidade: str, setor_selecionado: str, dados_equipamentos: Dict[str, str]) -> bool:
    """
    Regra de Negócio: Garante que a escolha do menu suspenso 'Setor' do site
    seja gravada ESTRITAMENTE na coluna 'Local / Setor'.
    """
    df, _ = carregar_dados_excel(unidade)
    
    # Prepara o dicionário de dados da linha
    nova_linha = {COLUNA_CHAVE: setor_selecionado.strip()}
    nova_linha.update(dados_equipamentos)
    
    # Atualiza se a linha do setor já existir, caso contrário adiciona nova linha
    mask = df[COLUNA_CHAVE].astype(str).str.strip().str.lower() == setor_selecionado.strip().lower()
    
    if mask.any():
        for k, v in dados_equipamentos.items():
            if v: # Atualiza apenas se houver valor fornecido
                df.loc[mask, k] = str(v).strip()
    else:
        df_nova = pd.DataFrame([nova_linha])
        df = pd.concat([df, df_nova], ignore_index=True)
        
    return salvar_no_excel(df, unidade)

def salvar_no_excel(df: pd.DataFrame, unidade: str) -> bool:
    """
    Grava os dados exclusivamente com a coluna 'Local / Setor' na Coluna A.
    """
    sucesso_sheets = False
    planilha = conectar_google_sheets()
    nome_aba = re.sub(r'[^a-zA-Z0-9_ ]', '_', unidade)[:30].strip()
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"

    # Aplica filtro que expurga totalmente a coluna 'Setor'
    df_salvar = expurgar_e_normalizar_setores(df).fillna("").astype(str)

    if planilha:
        try:
            try:
                aba = planilha.worksheet(nome_aba)
            except gspread.exceptions.WorksheetNotFound:
                aba = planilha.add_worksheet(title=nome_aba, rows="100", cols="20")

            aba.clear()
            valores = [df_salvar.columns.tolist()] + df_salvar.values.tolist()
            aba.update(values=valores, range_name="A1")
            
            aplicar_estilizacao_sheets(aba, len(valores), len(df_salvar.columns))
            sucesso_sheets = True
        except Exception as e:
            st.error(f"⚠️ Erro ao gravar no Google Sheets: {e}")

    try:
        df_salvar.to_excel(nome_arquivo_local, index=False)
    except Exception as e:
        st.error(f"Erro no backup local: {e}")

    carregar_dados_excel.clear()
    return sucesso_sheets or os.path.exists(nome_arquivo_local)

def excluir_setor(setor: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    if not df.empty and COLUNA_CHAVE in df.columns:
        setor_limpo = setor.strip().lower()
        mask_manter = df[COLUNA_CHAVE].astype(str).str.strip().str.lower() != setor_limpo
        df_filtrado = df[mask_manter]
        return salvar_no_excel(df_filtrado, unidade)
    return False

def excluir_patrimonio(setor: str, coluna: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    if not df.empty and COLUNA_CHAVE in df.columns and coluna in df.columns:
        df = df.fillna("").astype(str)
        coluna_fabricante = formatar_nome_fabricante(coluna)
        
        mask = df[COLUNA_CHAVE].astype(str).str.strip().str.lower() == setor.strip().lower()
        if mask.any():
            df.loc[mask, coluna] = ""
            if coluna_fabricante in df.columns:
                df.loc[mask, coluna_fabricante] = ""
            
            cols_dados = [c for c in df.columns if c != COLUNA_CHAVE]
            mask_vazia = df[cols_dados].apply(lambda row: "".join(row.values).strip() == "", axis=1)
            df = df[~mask_vazia]

            return salvar_no_excel(df, unidade)
    return False