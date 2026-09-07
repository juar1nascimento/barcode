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

# Estrutura Oficial em Ordem Alfabética por Equipamento
ORDEM_COLUNAS_OFICIAL = [
    "Local / Setor",
    "CPU - Nº de Patrimônio", "Fabricante CPU",
    "Estabilizador - Nº de Patrimônio", "Fabricante Estabilizador",
    "Impressora - Nº de Patrimônio", "Fabricante Impressora",
    "Monitores - Nº de Patrimônio", "Fabricante dos Monitores",
    "Mouse - Nº de Patrimônio", "Fabricante Mouse",
    "Nobreak - Nº de Patrimônio", "Fabricante Nobreak",
    "Switch - Nº de Patrimônio", "Fabricante Switch",
    "Teclado - Nº de Patrimônio", "Fabricante Teclado"
]

SETORES_PADRAO = ["Recepção", "Triagem", "Farmácia", "Consultório", "Almoxarifado"]
LISTA_URS_PADRAO = ["URS I", "URS II", "URS III"]
LISTA_UBS_PADRAO = ["UBS Central", "UBS Jardim", "UBS Vila Nova"]

# Mapeamento para redirecionar nomes duplicados/alternativos para a coluna única e oficial
MAPA_RENOMEAR_COLUNAS = {
    "Computador - Nº de Patrimônio": "CPU - Nº de Patrimônio",
    "Fabricante Computador": "Fabricante CPU",
    "Fabricante do Computador": "Fabricante CPU",
    "Monitor - Nº de Patrimônio": "Monitores - Nº de Patrimônio",
    "Fabricante Monitor": "Fabricante dos Monitores",
    "Fabricante do Monitor": "Fabricante dos Monitores",
    "Fabricante do Teclado": "Fabricante Teclado",
    "Fabricante do Mouse": "Fabricante Mouse",
    "Fabricante da Impressora": "Fabricante Impressora",
    "Fabricante do Nobreak": "Fabricante Nobreak"
}

def formatar_nome_patrimonio(patrimonio: str) -> str:
    p_limpo = patrimonio.strip()
    if not re.search(r'-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$', p_limpo, flags=re.IGNORECASE):
        p_limpo = f"{p_limpo} - Nº de Patrimônio"
    return MAPA_RENOMEAR_COLUNAS.get(p_limpo, p_limpo)

def formatar_nome_fabricante(patrimonio: str) -> str:
    p_limpo = re.sub(r'\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$', '', patrimonio.strip(), flags=re.IGNORECASE)
    if "monitor" in p_limpo.lower():
        return "Fabricante dos Monitores"
    nome_fab = f"Fabricante {p_limpo}"
    return MAPA_RENOMEAR_COLUNAS.get(nome_fab, nome_fab)

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
    Padroniza, consolida colunas duplicadas, elimina colunas desnecessárias,
    ordena as colunas em ordem alfabética de equipamento e ordena as linhas por setor.
    """
    df = df.copy()
    
    # 1. Elimina coluna antiga 'Setor' migrando valores para 'Local / Setor'
    if "Setor" in df.columns:
        if COLUNA_CHAVE in df.columns:
            df[COLUNA_CHAVE] = df[COLUNA_CHAVE].replace("", np.nan).fillna(df["Setor"]).fillna("")
        else:
            df[COLUNA_CHAVE] = df["Setor"]
        df = df.drop(columns=["Setor"])

    # 2. Consolida dados de colunas duplicadas/renomeadas antes de excluí-las
    for col_antiga, col_oficial in MAPA_RENOMEAR_COLUNAS.items():
        if col_antiga in df.columns:
            if col_oficial not in df.columns:
                df[col_oficial] = df[col_antiga]
            else:
                df[col_oficial] = df[col_oficial].replace("", np.nan).fillna(df[col_antiga]).fillna("")
            df = df.drop(columns=[col_antiga])

    # 3. Elimina colunas obsoletas
    cols_para_remover = [c for c in COLUNAS_OBSOLETAS if c in df.columns]
    if cols_para_remover:
        df = df.drop(columns=cols_para_remover)

    # 4. Assegura coluna Chave
    if COLUNA_CHAVE not in df.columns:
        df.insert(0, COLUNA_CHAVE, "")

    # 5. Garante estritamente apenas as colunas oficiais no DataFrame
    for col in ORDEM_COLUNAS_OFICIAL:
        if col not in df.columns:
            df[col] = ""

    # 6. Ordena as linhas alfabeticamente pela coluna 'Local / Setor'
    df = df.sort_values(by=COLUNA_CHAVE, ascending=True, key=lambda x: x.str.lower())

    # 7. Retorna o DataFrame mantendo estritamente a ordem de colunas oficial
    return df[ORDEM_COLUNAS_OFICIAL]

def remover_coluna_setor_da_planilha(aba: gspread.Worksheet):
    """Verifica se a Coluna A é 'Setor' e faz a exclusão física na aba do Google Sheets."""
    try:
        primeira_linha = aba.row_values(1)
        if primeira_linha and primeira_linha[0].strip().lower() == "setor":
            aba.delete_columns(1)
    except Exception:
        pass

def aplicar_estilizacao_sheets(aba: gspread.Worksheet, total_linhas: int, total_colunas: int):
    """Aplica formatação visual no Google Sheets."""
    try:
        aba.freeze(rows=1)
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
    """Carrega dados do Google Sheets organizando colunas e eliminando duplicatas."""
    planilha = conectar_google_sheets()
    nome_aba = re.sub(r'[^a-zA-Z0-9_ ]', '_', unidade)[:30].strip()
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"

    if planilha:
        try:
            aba = planilha.worksheet(nome_aba)
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
                return pd.DataFrame(columns=ORDEM_COLUNAS_OFICIAL), f"Google Sheets ({nome_aba})"
        except gspread.exceptions.WorksheetNotFound:
            pass
        except Exception as e:
            st.error(f"Erro ao ler do Google Sheets: {e}")

    if os.path.exists(nome_arquivo_local):
        try:
            df = pd.read_excel(nome_arquivo_local, dtype=str)
            df = df.fillna("")
            df = expurgar_e_normalizar_setores(df)
            return df, nome_arquivo_local
        except Exception:
            pass

    return pd.DataFrame(columns=ORDEM_COLUNAS_OFICIAL), nome_arquivo_local

def adicionar_e_salvar_sem_sobrescrever(
    codigo: str, patrimonio: str, setor: str, unidade: str, fabricante: str = ""
) -> bool:
    """Cadastra um patrimônio individual redirecionando estritamente para a coluna oficial."""
    setor_limpo = setor.strip()
    codigo_limpo = codigo.strip()
    fabricante_limpo = fabricante.strip()
    
    patrimonio_col = formatar_nome_patrimonio(patrimonio)
    coluna_fabricante = formatar_nome_fabricante(patrimonio)

    if not setor_limpo or not codigo_limpo or not patrimonio_col or not unidade:
        return False

    dados_envio = {
        patrimonio_col: codigo_limpo,
        coluna_fabricante: fabricante_limpo
    }
    
    return adicionar_ou_atualizar_registro(unidade, setor_limpo, dados_envio)

def adicionar_ou_atualizar_registro(unidade: str, setor_selecionado: str, dados_equipamentos: Dict[str, str]) -> bool:
    """Insere/atualiza registros garantindo o uso exclusivo das colunas oficiais."""
    df, _ = carregar_dados_excel(unidade)
    setor_limpo = setor_selecionado.strip()
    
    # Redireciona chaves recebidas para o mapa de nomenclatura oficial
    dados_normalizados = {}
    for k, v in dados_equipamentos.items():
        col_destino = MAPA_RENOMEAR_COLUNAS.get(k, k)
        if col_destino in ORDEM_COLUNAS_OFICIAL:
            dados_normalizados[col_destino] = v

    indices_setor = df[df[COLUNA_CHAVE].astype(str).str.strip().str.lower() == setor_limpo.lower()].index
    linha_destino_idx = None

    if len(indices_setor) > 0:
        for idx in indices_setor:
            colisoes = False
            for col, val in dados_normalizados.items():
                if val and col in df.columns:
                    val_atual = str(df.at[idx, col]).strip()
                    if val_atual != "":
                        colisoes = True
                        break
            if not colisoes:
                linha_destino_idx = idx
                break

    if linha_destino_idx is None:
        nova_linha = {c: "" for c in ORDEM_COLUNAS_OFICIAL}
        nova_linha[COLUNA_CHAVE] = setor_limpo
        for col, val in dados_normalizados.items():
            if val and col in nova_linha:
                nova_linha[col] = str(val).strip()
        
        df_nova = pd.DataFrame([nova_linha])
        df = pd.concat([df, df_nova], ignore_index=True)
    else:
        for col, val in dados_normalizados.items():
            if val and col in df.columns:
                df.at[linha_destino_idx, col] = str(val).strip()

    return salvar_no_excel(df, unidade)

def salvar_no_excel(df: pd.DataFrame, unidade: str) -> bool:
    """Salva os dados no Google Sheets mantendo a estrutura limpa e organizada."""
    sucesso_sheets = False
    planilha = conectar_google_sheets()
    nome_aba = re.sub(r'[^a-zA-Z0-9_ ]', '_', unidade)[:30].strip()
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"

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

    st.cache_data.clear()
    return sucesso_sheets or os.path.exists(nome_arquivo_local)

def excluir_setor(setor: str, unidade: str) -> bool:
    """Exclui todas as entradas de um setor específico."""
    df, _ = carregar_dados_excel(unidade)
    if not df.empty and COLUNA_CHAVE in df.columns:
        setor_limpo = setor.strip().lower()
        mask_manter = df[COLUNA_CHAVE].astype(str).str.strip().str.lower() != setor_limpo
        df_filtrado = df[mask_manter]
        return salvar_no_excel(df_filtrado, unidade)
    return False

def excluir_patrimonio(setor: str, coluna: str, unidade: str) -> bool:
    """Exclui o código do patrimônio e o fabricante associado."""
    df, _ = carregar_dados_excel(unidade)
    coluna_oficial = MAPA_RENOMEAR_COLUNAS.get(coluna, coluna)

    if not df.empty and COLUNA_CHAVE in df.columns and coluna_oficial in df.columns:
        df = df.fillna("").astype(str)
        coluna_fabricante = formatar_nome_fabricante(coluna_oficial)
        
        mask = df[COLUNA_CHAVE].astype(str).str.strip().str.lower() == setor.strip().lower()
        if mask.any():
            df.loc[mask, coluna_oficial] = ""
            if coluna_fabricante in df.columns:
                df.loc[mask, coluna_fabricante] = ""
            
            cols_dados = [c for c in df.columns if c != COLUNA_CHAVE]
            mask_vazia = df[cols_dados].apply(lambda row: "".join(row.values).strip() == "", axis=1)
            df = df[~mask_vazia]

            return salvar_no_excel(df, unidade)
    return False