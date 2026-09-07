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

# Ordem oficial: equipamento em ordem alfabética, sempre Patrimônio + Fabricante lado a lado.
ORDEM_COLUNAS_OFICIAL = [
    "Local / Setor",
    "CPU - Nº de Patrimônio", "Fabricante CPU",
    "Estabilizador - Nº de Patrimônio", "Fabricante Estabilizador",
    "Impressora - Nº de Patrimônio", "Fabricante Impressora",
    "Monitores - Nº de Patrimônio", "Fabricante dos Monitores",
    "Mouse - Nº de Patrimônio", "Fabricante Mouse",
    "Nobreak - Nº de Patrimônio", "Fabricante Nobreak",
    "Switch - Nº de Patrimônio", "Fabricante Switch",
    "Teclado - Nº de Patrimônio", "Fabricante Teclado",
]

# Nomes aceitos na entrada são convertidos para UMA ÚNICA coluna canônica.
# A regra evita que variações como "Monitor", "Monitores" ou
# "Fabricante do Monitor" criem novas colunas.
MAPA_RENOMEAR_COLUNAS = {
    # Local
    "Setor": "Local / Setor",
    "Local": "Local / Setor",
    "Local/Setor": "Local / Setor",

    # CPU / Computador
    "Computador - Nº de Patrimônio": "CPU - Nº de Patrimônio",
    "Computador - N° de Patrimônio": "CPU - Nº de Patrimônio",
    "CPU - N° de Patrimônio": "CPU - Nº de Patrimônio",
    "CPU - No de Patrimônio": "CPU - Nº de Patrimônio",
    "Fabricante Computador": "Fabricante CPU",
    "Fabricante do Computador": "Fabricante CPU",
    "Fabricante CPU": "Fabricante CPU",

    # Estabilizador
    "Estabilizador - N° de Patrimônio": "Estabilizador - Nº de Patrimônio",
    "Fabricante do Estabilizador": "Fabricante Estabilizador",
    "Fabricante Estabilizador": "Fabricante Estabilizador",

    # Impressora
    "Impressora - N° de Patrimônio": "Impressora - Nº de Patrimônio",
    "Fabricante da Impressora": "Fabricante Impressora",
    "Fabricante Impressora": "Fabricante Impressora",

    # Monitor
    "Monitor - Nº de Patrimônio": "Monitores - Nº de Patrimônio",
    "Monitor - N° de Patrimônio": "Monitores - Nº de Patrimônio",
    "Monitores - N° de Patrimônio": "Monitores - Nº de Patrimônio",
    "Fabricante Monitor": "Fabricante dos Monitores",
    "Fabricante do Monitor": "Fabricante dos Monitores",
    "Fabricante Monitores": "Fabricante dos Monitores",
    "Fabricante dos Monitores": "Fabricante dos Monitores",

    # Mouse
    "Mouse - N° de Patrimônio": "Mouse - Nº de Patrimônio",
    "Fabricante do Mouse": "Fabricante Mouse",
    "Fabricante Mouse": "Fabricante Mouse",

    # Nobreak
    "Nobreak - N° de Patrimônio": "Nobreak - Nº de Patrimônio",
    "Fabricante do Nobreak": "Fabricante Nobreak",
    "Fabricante Nobreak": "Fabricante Nobreak",

    # Switch
    "Switch - N° de Patrimônio": "Switch - Nº de Patrimônio",
    "Fabricante do Switch": "Fabricante Switch",
    "Fabricante Switch": "Fabricante Switch",

    # Teclado
    "Teclado - N° de Patrimônio": "Teclado - Nº de Patrimônio",
    "Fabricante do Teclado": "Fabricante Teclado",
    "Fabricante Teclado": "Fabricante Teclado",
}

def _normalizar_nome_coluna(nome: str) -> str:
    """Normaliza espaços, acentos de variações comuns e símbolos para comparação."""
    nome = str(nome or "").strip()
    nome = re.sub(r"\s+", " ", nome)
    nome = nome.replace("N°", "Nº").replace("No", "Nº")
    nome = nome.replace("Nº.", "Nº")
    return nome

def _coluna_canonica(nome: str) -> str:
    """Retorna a coluna oficial sem criar uma nova coluna para variações."""
    nome = _normalizar_nome_coluna(nome)
    if nome in ORDEM_COLUNAS_OFICIAL:
        return nome

    # Primeiro tenta o mapa explícito.
    if nome in MAPA_RENOMEAR_COLUNAS:
        return MAPA_RENOMEAR_COLUNAS[nome]

    # Depois aplica comparação flexível para diferenças de singular/plural,
    # "do/da/dos" e N°/Nº.
    chave = nome.lower()
    chave = re.sub(r"\s+", " ", chave)
    chave = chave.replace("n°", "nº")
    chave = re.sub(r"\bfabricante (do|da|dos|das)\b", "fabricante", chave)
    chave = chave.replace("monitores", "monitor")

    for oficial in ORDEM_COLUNAS_OFICIAL:
        ko = oficial.lower().replace("monitores", "monitor")
        ko = re.sub(r"\bfabricante\b", "fabricante", ko)
        ko = re.sub(r"\s+", " ", ko)
        if chave == ko:
            return oficial

    return nome

def consolidar_colunas_sem_repeticao(df: pd.DataFrame) -> pd.DataFrame:
    """
    Regra central de deduplicação:
    1. Toda coluna recebida é convertida para o nome canônico.
    2. Colunas que apontam para o mesmo nome são mescladas.
    3. Quando houver duas colunas equivalentes, mantém o primeiro valor
       preenchido e usa a segunda apenas para preencher células vazias.
    4. Nenhuma coluna fora da ordem oficial é preservada.
    """
    df = df.copy()
    resultado = pd.DataFrame(index=df.index)

    for coluna in df.columns:
        canonica = _coluna_canonica(coluna)

        if canonica not in ORDEM_COLUNAS_OFICIAL:
            # Ignora colunas desconhecidas para impedir colunas extras.
            continue

        serie = df[coluna].fillna("").astype(str).str.strip()

        if canonica not in resultado.columns:
            resultado[canonica] = serie
        else:
            atual = resultado[canonica].fillna("").astype(str).str.strip()
            vazio = atual.eq("")
            resultado.loc[vazio, canonica] = serie.loc[vazio]

    # Garante todas as colunas oficiais, uma única vez.
    for coluna in ORDEM_COLUNAS_OFICIAL:
        if coluna not in resultado.columns:
            resultado[coluna] = ""

    return resultado[ORDEM_COLUNAS_OFICIAL]


SETORES_PADRAO = ["Recepção", "Triagem", "Farmácia", "Consultório", "Almoxarifado"]
LISTA_URS_PADRAO = ["URS I", "URS II", "URS III"]
LISTA_UBS_PADRAO = ["UBS Central", "UBS Jardim", "UBS Vila Nova"]

# Mapeamento para redirecionar nomes duplicados/alternativos para a coluna única e oficial

def formatar_nome_patrimonio(patrimonio: str) -> str:
    p_limpo = patrimonio.strip()
    if not re.search(r'-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$', p_limpo, flags=re.IGNORECASE):
        return f"{p_limpo} - Nº de Patrimônio"
    return p_limpo

def formatar_nome_fabricante(patrimonio: str) -> str:
    p_limpo = re.sub(r'\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$', '', patrimonio.strip(), flags=re.IGNORECASE)
    if "monitor" in p_limpo.lower():
        return "Fabricante dos Monitores"
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
    Padroniza a tabela e impede colunas repetidas.
    A ordem final é sempre:
    Local / Setor + equipamento em ordem alfabética +
    Nº de Patrimônio ao lado do respectivo Fabricante.
    """
    df = df.copy().fillna("").astype(str)

    # Consolida TODAS as variações antes de ordenar.
    df = consolidar_colunas_sem_repeticao(df)

    # Remove linhas completamente vazias, preservando o cabeçalho.
    if not df.empty:
        colunas_dados = [c for c in ORDEM_COLUNAS_OFICIAL if c != COLUNA_CHAVE]
        mascara_vazia = (
            df[ORDEM_COLUNAS_OFICIAL]
            .fillna("")
            .astype(str)
            .apply(lambda linha: all(str(v).strip() == "" for v in linha), axis=1)
        )
        df = df[~mascara_vazia].copy()

    # Ordena alfabeticamente por Local / Setor.
    df[COLUNA_CHAVE] = df[COLUNA_CHAVE].fillna("").astype(str).str.strip()
    df = df.sort_values(
        by=COLUNA_CHAVE,
        ascending=True,
        key=lambda x: x.str.casefold(),
        kind="stable"
    )

    return df[ORDEM_COLUNAS_OFICIAL]

def remover_coluna_setor_da_planilha(aba: gspread.Worksheet):
    """
    Verifica se a Coluna A é 'Setor' e faz a exclusão física na aba do Google Sheets.
    """
    try:
        primeira_linha = aba.row_values(1)
        if primeira_linha and primeira_linha[0].strip().lower() == "setor":
            aba.delete_columns(1)
    except Exception:
        pass

def aplicar_estilizacao_sheets(aba: gspread.Worksheet, total_linhas: int, total_colunas: int):
    """
    Aplica um leiaute moderno e corporativo ao Google Sheets:
    - cabeçalho destacado e congelado
    - filtros
    - larguras adequadas por tipo de coluna
    - alinhamento e quebra de texto
    - bordas discretas
    - linhas alternadas para facilitar leitura
    - coluna Local / Setor em destaque
    """
    try:
        ultima_coluna = gspread.utils.rowcol_to_a1(1, total_colunas).replace("1", "")
        ultima_linha = max(total_linhas, 2)

        # Congela o cabeçalho.
        aba.freeze(rows=1)

        # Cabeçalho: visual corporativo.
        aba.format(f"A1:{gspread.utils.rowcol_to_a1(1, total_colunas)}", {
            "backgroundColor": {"red": 0.10, "green": 0.24, "blue": 0.38},
            "textFormat": {
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "bold": True,
                "fontSize": 10
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
            "wrapStrategy": "WRAP"
        })

        # Dados.
        if total_linhas > 1:
            intervalo = f"A2:{gspread.utils.rowcol_to_a1(total_linhas, total_colunas)}"
            aba.format(intervalo, {
                "textFormat": {"fontSize": 9},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
                "borders": {
                    "top": {"style": "SOLID", "width": 1, "color": {"red": 0.86, "green": 0.88, "blue": 0.90}},
                    "bottom": {"style": "SOLID", "width": 1, "color": {"red": 0.86, "green": 0.88, "blue": 0.90}},
                    "left": {"style": "SOLID", "width": 1, "color": {"red": 0.86, "green": 0.88, "blue": 0.90}},
                    "right": {"style": "SOLID", "width": 1, "color": {"red": 0.86, "green": 0.88, "blue": 0.90}}
                }
            })

        # Altura do cabeçalho.
        aba.set_row_height(1, 34)

        # Larguras: setor maior; patrimônio e fabricante equilibrados.
        for idx, nome_coluna in enumerate(aba.row_values(1), start=1):
            if nome_coluna == "Local / Setor":
                largura = 155
            elif "Nº de Patrimônio" in nome_coluna:
                largura = 125
            elif "Fabricante" in nome_coluna:
                largura = 125
            else:
                largura = 120
            aba.set_column_width(idx, largura)

        # Filtro automático em toda a tabela.
        try:
            aba.clear_basic_filter()
        except Exception:
            pass
        if total_linhas >= 1:
            aba.set_basic_filter(
                f"A1:{gspread.utils.rowcol_to_a1(total_linhas, total_colunas)}"
            )

        # Destaca visualmente a coluna principal "Local / Setor".
        try:
            aba.format(f"A2:A{ultima_linha}", {
                "textFormat": {"bold": True, "fontSize": 9},
                "horizontalAlignment": "LEFT",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP"
            })
        except Exception:
            pass

        # Formatação condicional para linhas alternadas (zebra).
        try:
            aba.add_conditional_format(
                f"A2:{gspread.utils.rowcol_to_a1(total_linhas, total_colunas)}",
                {
                    "addConditionalFormatRule": {
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": "=ISEVEN(ROW())"}]
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 0.96, "green": 0.97, "blue": 0.98
                                }
                            }
                        },
                        "index": 0
                    }
                }
            )
        except Exception:
            # Compatibilidade com versões do gspread sem suporte a essa API.
            pass

    except Exception as e:
        st.warning(f"Não foi possível aplicar toda a estilização: {e}")

@st.cache_data(ttl=2)
def carregar_dados_excel(unidade: str) -> Tuple[pd.DataFrame, str]:
    """
    Carrega dados do Google Sheets organizando colunas e eliminando duplicatas.
    """
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

    # Backup Local
    if os.path.exists(nome_arquivo_local):
        try:
            df = pd.read_excel(nome_arquivo_local, dtype=str)
            df = df.fillna("")
            df = expurgar_e_normalizar_setores(df)
            return df, nome_arquivo_local
        except Exception:
            pass

    return pd.DataFrame(columns=ORDEM_COLUNAS_OFICIAL), nome_arquivo_local

def adicionar_ou_atualizar_registro(unidade: str, setor_selecionado: str, dados_equipamentos: Dict[str, str]) -> bool:
    """
    Insere/atualiza registros garantindo o uso exclusivo das colunas oficiais.
    """
    df, _ = carregar_dados_excel(unidade)
    setor_limpo = setor_selecionado.strip()
    
    # Redireciona chaves recebidas para o mapa de nomenclatura oficial
    dados_normalizados = {}
    for k, v in dados_equipamentos.items():
        col_destino = MAPA_RENOMEAR_COLUNAS.get(k, k)
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
        nova_linha = {c: "" for c in df.columns}
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
    """
    Salva os dados no Google Sheets mantendo o leiaute limpo, organizado e reordenado.
    """
    sucesso_sheets = False
    planilha = conectar_google_sheets()
    nome_aba = re.sub(r'[^a-zA-Z0-9_ ]', '_', unidade)[:30].strip()
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"

    # Aplica normalização e ordenação estrita antes do salvamento
    df_salvar = expurgar_e_normalizar_setores(df).fillna("").astype(str)

    # Garantia final: cabeçalho único e na ordem oficial.
    if list(df_salvar.columns) != ORDEM_COLUNAS_OFICIAL:
        df_salvar = df_salvar.reindex(columns=ORDEM_COLUNAS_OFICIAL, fill_value="")

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