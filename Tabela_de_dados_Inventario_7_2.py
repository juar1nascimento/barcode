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
COLUNA_CHAVE = "Setor"
COLUNAS_OBSOLETAS = ["Data_Hora", "Usuario", "Status"]
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
        # Busca no bloco de conexões do Streamlit Secrets
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
        
        # Mapeia as credenciais do Service Account
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
        
        # Pega a URL da planilha a partir do campo 'spreadsheet'
        sheet_url = sec_gsheets.get("spreadsheet") or st.secrets.get("spreadsheet_url")
        if sheet_url:
            return client.open_by_url(sheet_url)

    except Exception as e:
        st.warning(f"Não foi possível conectar ao Google Sheets: {e}")
    return None

@st.cache_data(ttl=2)
def carregar_dados_excel(unidade: str) -> Tuple[pd.DataFrame, str]:
    """
    Carrega os dados da aba da unidade no Google Sheets.
    """
    planilha = conectar_google_sheets()
    nome_aba = re.sub(r'[^a-zA-Z0-9_ ]', '_', unidade)[:30].strip()
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"

    if planilha:
        try:
            aba = planilha.worksheet(nome_aba)
            dados = aba.get_all_records(expected_headers=[])
            if dados:
                df = pd.DataFrame(dados)
                df = df.fillna("").astype(str)
                if COLUNA_CHAVE not in df.columns:
                    df.insert(0, COLUNA_CHAVE, "")
                return df, f"Google Sheets ({nome_aba})"
            else:
                return pd.DataFrame(columns=[COLUNA_CHAVE] + COLUNAS_PADRAO), f"Google Sheets ({nome_aba})"
        except gspread.exceptions.WorksheetNotFound:
            pass # A aba será criada automaticamente quando houver a primeira gravação
        except Exception as e:
            st.error(f"Erro ao ler do Google Sheets: {e}")

    # Fallback Local
    if os.path.exists(nome_arquivo_local):
        try:
            df = pd.read_excel(nome_arquivo_local, dtype=str)
            return df.fillna(""), nome_arquivo_local
        except Exception:
            pass

    return pd.DataFrame(columns=[COLUNA_CHAVE] + COLUNAS_PADRAO), nome_arquivo_local

def salvar_no_excel(df: pd.DataFrame, unidade: str) -> bool:
    """
    Salva/Atualiza o DataFrame no Google Sheets e cria o backup local.
    """
    sucesso_sheets = False
    planilha = conectar_google_sheets()
    nome_aba = re.sub(r'[^a-zA-Z0-9_ ]', '_', unidade)[:30].strip()
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"

    df_salvar = df.copy().fillna("").astype(str)
    if COLUNA_CHAVE in df_salvar.columns:
        cols = [COLUNA_CHAVE] + [c for c in df_salvar.columns if c != COLUNA_CHAVE]
        df_salvar = df_salvar[cols]

    # 1. Atualizar no Google Sheets
    if planilha:
        try:
            try:
                aba = planilha.worksheet(nome_aba)
            except gspread.exceptions.WorksheetNotFound:
                aba = planilha.add_worksheet(title=nome_aba, rows="100", cols="20")

            valores = [df_salvar.columns.tolist()] + df_salvar.values.tolist()
            aba.clear()
            aba.update(values=valores, range_name="A1")
            sucesso_sheets = True
        except Exception as e:
            st.error(f"⚠️ Erro ao gravar no Google Sheets: {e}")

    # 2. Backup Local
    try:
        df_salvar.to_excel(nome_arquivo_local, index=False)
    except Exception as e:
        st.error(f"Erro no backup local: {e}")

    carregar_dados_excel.clear()
    return sucesso_sheets or os.path.exists(nome_arquivo_local)

def _aplicar_exclusao_setor(df: pd.DataFrame, setor: str) -> tuple[pd.DataFrame, bool]:
    """Aplica a exclusão de setor em memória e informa se houve alteração."""
    if df.empty or COLUNA_CHAVE not in df.columns:
        return df.copy(), False
    setor_limpo = str(setor or "").strip().casefold()
    if not setor_limpo:
        return df.copy(), False
    valores_setor = df[COLUNA_CHAVE].astype(str).str.strip().str.casefold()
    mask_excluir = valores_setor == setor_limpo
    if not mask_excluir.any():
        return df.copy(), False
    return df.loc[~mask_excluir].copy(), True


def _aplicar_exclusao_patrimonio(df: pd.DataFrame, setor: str, coluna: str) -> tuple[pd.DataFrame, bool]:
    """Limpa patrimônio + fabricante somente no setor escolhido."""
    if df.empty or COLUNA_CHAVE not in df.columns or coluna not in df.columns:
        return df.copy(), False
    df_trabalho = df.fillna("").astype(str).copy()
    setor_limpo = str(setor or "").strip().casefold()
    coluna_limpa = str(coluna or "").strip()
    if not setor_limpo or not coluna_limpa:
        return df_trabalho, False
    mask_setor = df_trabalho[COLUNA_CHAVE].str.strip().str.casefold() == setor_limpo
    if not mask_setor.any():
        return df_trabalho, False
    coluna_fabricante = formatar_nome_fabricante(coluna_limpa)
    df_trabalho.loc[mask_setor, coluna_limpa] = ""
    if coluna_fabricante in df_trabalho.columns:
        df_trabalho.loc[mask_setor, coluna_fabricante] = ""
    cols_dados = [c for c in df_trabalho.columns if c != COLUNA_CHAVE]
    if cols_dados:
        mask_linha_vazia = df_trabalho[cols_dados].apply(
            lambda row: all(str(v).strip().lower() in {"", "nan", "none", "null", "<na>"} for v in row),
            axis=1,
        )
        df_trabalho = df_trabalho.loc[~mask_linha_vazia].copy()
    return df_trabalho, True


def excluir_setor(setor: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    df_filtrado, alterado = _aplicar_exclusao_setor(df, setor)
    if not alterado:
        return False
    return salvar_no_excel(df_filtrado, unidade)


def excluir_patrimonio(setor: str, coluna: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    df_filtrado, alterado = _aplicar_exclusao_patrimonio(df, setor, coluna)
    if not alterado:
        return False
    return salvar_no_excel(df_filtrado, unidade)
