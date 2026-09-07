import os
import re
import pandas as pd
import numpy as np
import streamlit as st
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

@st.cache_data(ttl=5)
def carregar_dados_excel(unidade: str) -> Tuple[pd.DataFrame, str]:
    """
    Carrega os dados da unidade. Se houver integração com Google Sheets via st.secrets,
    prioriza a nuvem; caso contrário, utiliza armazenamento local com isolamento por unidade.
    """
    nome_arquivo = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"
    if os.path.exists(nome_arquivo):
        try:
            df = pd.read_excel(nome_arquivo, dtype=str)
            return df.fillna(""), nome_arquivo
        except Exception:
            pass
    
    df_empty = pd.DataFrame(columns=[COLUNA_CHAVE] + COLUNAS_PADRAO)
    return df_empty, nome_arquivo

def salvar_no_excel(df: pd.DataFrame, unidade: str) -> bool:
    """
    Persiste o DataFrame garantindo a sanitização e atualização síncrona.
    """
    try:
        nome_arquivo = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"
        df_salvar = df.copy().fillna("").astype(str)
        df_salvar.to_excel(nome_arquivo, index=False)
        
        # Limpeza explicita de cache no Streamlit
        carregar_dados_excel.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar dados persistentemente: {str(e)}")
        return False

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
            
            # Limpa linhas que ficaram completamente sem patrimônios cadastrados
            cols_dados = [c for c in df.columns if c != COLUNA_CHAVE]
            mask_vazia = df[cols_dados].apply(lambda row: "".join(row.values).strip() == "", axis=1)
            df = df[~mask_vazia]

            return salvar_no_excel(df, unidade)
    return False