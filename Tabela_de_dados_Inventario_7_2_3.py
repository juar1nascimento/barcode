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
# Atualizado para utilizar 'Local / Setor' conforme a planilha
COLUNA_CHAVE = "Local / Setor"
COLUNAS_OBSOLETAS = ["Data_Hora", "Usuario", "Status", "Setor"] # Incluída a antiga coluna 'Setor'
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

def normalizar_df_setor(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garante que a coluna 'Local / Setor' herde os dados do menu/seleção do site,
    migra dados da antiga coluna 'Setor' se existirem e exclui a coluna 'Setor'.
    """
    df = df.copy()
    
    # Se a antiga coluna 'Setor' existir no DataFrame
    if "Setor" in df.columns:
        if COLUNA_CHAVE not in df.columns:
            df[COLUNA_CHAVE] = df["Setor"]
        else:
            # Copia dados da coluna 'Setor' caso 'Local / Setor' esteja vazia
            df[COLUNA_CHAVE] = df[COLUNA_CHAVE].replace("", np.nan).fillna(df["Setor"]).fillna("")
        
        # Remove a antiga coluna 'Setor'
        df = df.drop(columns=["Setor"])

    # Se a coluna 'Local / Setor' ainda não existir, cria como primeira coluna
    if COLUNA_CHAVE not in df.columns:
        df.insert(0, COLUNA_CHAVE, "")
        
    return df

@st.cache_data(ttl=2)
def carregar_dados_excel(unidade: str) -> Tuple[pd.DataFrame, str]:
    """
    Carrega os dados da aba da unidade no Google Sheets, aplicando a normalização do 'Local / Setor'.
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
                df = normalizar_df_setor(df)
                return df, f"Google Sheets ({nome_aba})"
            else:
                return pd.DataFrame(columns=[COLUNA_CHAVE] + COLUNAS_PADRAO), f"Google Sheets ({nome_aba})"
        except gspread.exceptions.WorksheetNotFound:
            pass
        except Exception as e:
            st.error(f"Erro ao ler do Google Sheets: {e}")

    # Fallback Local
    if os.path.exists(nome_arquivo_local):
        try:
            df = pd.read_excel(nome_arquivo_local, dtype=str)
            df = df.fillna("")
            df = normalizar_df_setor(df)
            return df, nome_arquivo_local
        except Exception:
            pass

    return pd.DataFrame(columns=[COLUNA_CHAVE] + COLUNAS_PADRAO), nome_arquivo_local

def salvar_no_excel(df: pd.DataFrame, unidade: str) -> bool:
    """
    Salva/Atualiza o DataFrame no Google Sheets garantindo que 'Local / Setor' seja a coluna principal.
    """
    sucesso_sheets = False
    planilha = conectar_google_sheets()
    nome_aba = re.sub(r'[^a-zA-Z0-9_ ]', '_', unidade)[:30].strip()
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"

    # Aplica a regra de remoção da coluna 'Setor' e fixação da 'Local / Setor'
    df_salvar = normalizar_df_setor(df).fillna("").astype(str)
    
    # Ordena as colunas garantindo 'Local / Setor' em primeiro lugar
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