import os
import re
from datetime import datetime
from typing import Optional, Tuple

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

from inventario_regras import (
    TIPOS_PATRIMONIO_OFICIAIS,
    SETORES_OFICIAIS,
    normalizar_setor,
    normalizar_fabricante,
    normalizar_dataframe_inventario,
    ordenar_inventario,
)

ARQUIVO_EXCEL = "inventario_dados.xlsx"
COLUNA_CHAVE = "Setor"
COLUNAS_OBSOLETAS = ["Data_Hora", "Usuario", "Status", "Fabricante", "Data Cadastro", "Origem"]
TIPOS_PATRIMONIO = TIPOS_PATRIMONIO_OFICIAIS
COLUNAS_INVENTARIO = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Código de Barras", "Fabricante", "Data Cadastro", "Origem", "Status"]
COLUNAS_PADRAO = COLUNAS_INVENTARIO.copy()
SETORES_PADRAO = list(SETORES_OFICIAIS)
LISTA_URS_PADRAO = ["URS Novo Horizonte", "URS Jacaraípe", "URS Boa Vista", "URS Feu Rosa", "URS Serra Sede", "URS Serra Dourada"]
LISTA_UBS_PADRAO = ["UBS André Carloni", "UBS Bairro de Fátima", "UBS Feu Rosa", "UBS Barcelona", "UBS Barro Branco", "UBS Campinho da Serra", "UBS Carapebus", "UBS Carapina Grande", "UBS Central Carapina", "UBS Cidade Continental", "UBS Eldorado", "UBS Jardim Carapina", "UBS Jardim Tropical", "UBS José de Anchieta", "UBS Laranjeiras Velha", "UBS Manguinhos", "UBS Manoel Plaza", "UBS Nova Almeida", "UBS Nova Carapina I", "UBS Nova Carapina II", "UBS Oceania", "UBS Pitanga", "UBS Planalto Serrano (Bloco A)", "UBS Planalto Serrano (Bloco B)", "UBS Porto Canoa", "UBS São Diogo", "UBS São Marcos", "UBS Taquara I", "UBS Taquara II", "UBS Vila Nova de Colares", "UBS Vista da Serra", "UBS Itinerante (atendimento na UBS)"]
UNIDADES_PADRAO = LISTA_URS_PADRAO + LISTA_UBS_PADRAO


def formatar_nome_patrimonio(patrimonio: str) -> str:
    return str(patrimonio or "").strip()


def formatar_nome_fabricante(patrimonio: str) -> str:
    p = re.sub(r"\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio$", "", str(patrimonio or "").strip(), flags=re.I)
    return f"Fabricante {p}" if p else "Fabricante"


def _normalizar_tipo(valor: str) -> str:
    valor = re.sub(r"\s+", " ", str(valor or "").strip())
    mapa = {"computador": "CPU", "cpu": "CPU", "monitor": "Monitores", "monitores": "Monitores", "teclado": "Teclado", "mouse": "Mouse", "impressora": "Imprenssoras", "impressoras": "Imprenssoras"}
    return mapa.get(valor.casefold(), valor if valor in TIPOS_PATRIMONIO else "Outros Dispositivos")


def _normalizar_unidade_aba(nome: str) -> str:
    aliases = {"URS Jacara_pe": "URS Jacaraípe", "UBS Bairro de F_tima": "UBS Bairro de Fátima"}
    return aliases.get(str(nome or "").strip(), str(nome or "").strip())


def _valor_texto(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if re.fullmatch(r"-?\d+\.0", s):
        s = s[:-2]
    return s


def _inferir_tipo_coluna(cabecalho: str) -> Optional[str]:
    h = _valor_texto(cabecalho).casefold()
    if "fabricante" in h or "setor" in h or "local" in h:
        return None
    if "computador" in h or re.search(r"\bcpu\b", h):
        return "CPU"
    if "monitor" in h:
        return "Monitores"
    if "teclado" in h:
        return "Teclado"
    if "mouse" in h:
        return "Mouse"
    if "impress" in h:
        return "Imprenssoras"
    return "Outros Dispositivos"


def _inferir_tipo_fabricante(cabecalho: str) -> Optional[str]:
    return _inferir_tipo_coluna(_valor_texto(cabecalho).casefold().replace("fabricante", "").strip())


def _normalizar_legacy_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUNAS_INVENTARIO)
    df = df.fillna("").copy()
    df.columns = [str(c).strip() for c in df.columns]
    if "Tipo de Patrimônio" in df.columns and "Código de Barras" in df.columns:
        resultado = df.reindex(columns=COLUNAS_INVENTARIO, fill_value="").fillna("").astype(str)
        resultado = normalizar_dataframe_inventario(resultado)
        return ordenar_inventario(resultado)
    setor_col = "Setor" if "Setor" in df.columns else (df.columns[0] if len(df.columns) else "Setor")
    registros = []
    for _, row in df.iterrows():
        setor = normalizar_setor(_valor_texto(row.get(setor_col, "")))
        if not setor:
            continue
        for col in df.columns:
            tipo = _inferir_tipo_coluna(col)
            if not tipo:
                continue
            valor = _valor_texto(row.get(col, ""))
            if not valor or valor.casefold() in {"none", "nan", "null"}:
                continue
            fabricante = ""
            for c2 in df.columns:
                if "fabricante" in str(c2).casefold() and _inferir_tipo_fabricante(c2) == tipo:
                    fabricante = normalizar_fabricante(_valor_texto(row.get(c2, "")))
                    break
            registros.append({"Setor": setor, "Tipo de Patrimônio": tipo, "Nº de Patrimônio": valor, "Código de Barras": "", "Fabricante": fabricante, "Data Cadastro": "", "Origem": "Migração do formato anterior", "Status": "Ativo"})
    resultado = pd.DataFrame(registros, columns=COLUNAS_INVENTARIO).fillna("").astype(str)
    return ordenar_inventario(resultado)


def conectar_google_sheets():
    try:
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            sec = st.secrets["connections"]["gsheets"]
        elif "gcp_service_account" in st.secrets:
            sec = st.secrets["gcp_service_account"]
        else:
            return None
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = {k: sec.get(k) for k in ("type", "project_id", "private_key_id", "private_key", "client_email", "client_id", "auth_uri", "token_uri", "auth_provider_x509_cert_url", "client_x509_cert_url")}
        creds_dict["type"] = creds_dict.get("type") or "service_account"
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet_url = sec.get("spreadsheet") or st.secrets.get("spreadsheet_url")
        return client.open_by_url(sheet_url) if sheet_url else None
    except Exception as e:
        st.warning(f"Não foi possível conectar ao Google Sheets: {e}")
        return None


def _nome_aba(unidade: str) -> str:
    return _normalizar_unidade_aba(unidade)[:90].strip()


@st.cache_data(ttl=2)
def carregar_dados_excel(unidade: str) -> Tuple[pd.DataFrame, str]:
    unidade = _normalizar_unidade_aba(unidade)
    planilha = conectar_google_sheets()
    nome_aba = _nome_aba(unidade)
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"
    if planilha:
        try:
            nomes = [nome_aba]
            if nome_aba == "URS Jacaraípe":
                nomes.append("URS Jacara_pe")
            elif nome_aba == "UBS Bairro de Fátima":
                nomes.append("UBS Bairro de F_tima")
            partes, fontes = [], []
            for nome in nomes:
                try:
                    aba = planilha.worksheet(nome)
                except gspread.exceptions.WorksheetNotFound:
                    continue
                valores = aba.get_all_values()
                if valores:
                    partes.append(_normalizar_legacy_dataframe(pd.DataFrame(valores[1:], columns=valores[0])))
                    fontes.append(nome)
            if partes:
                combinado = pd.concat(partes, ignore_index=True)
                combinado = _normalizar_legacy_dataframe(combinado).drop_duplicates(subset=["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Código de Barras"], keep="first")
                return ordenar_inventario(combinado.reindex(columns=COLUNAS_INVENTARIO, fill_value="")), f"Google Sheets ({' + '.join(fontes)})"
            return pd.DataFrame(columns=COLUNAS_INVENTARIO), f"Google Sheets ({nome_aba})"
        except Exception as e:
            st.error(f"Erro ao ler do Google Sheets: {e}")
    if os.path.exists(nome_arquivo_local):
        try:
            return _normalizar_legacy_dataframe(pd.read_excel(nome_arquivo_local, dtype=str)), nome_arquivo_local
        except Exception:
            pass
    return pd.DataFrame(columns=COLUNAS_INVENTARIO), nome_arquivo_local


def salvar_no_excel(df: pd.DataFrame, unidade: str) -> bool:
    unidade = _normalizar_unidade_aba(unidade)
    df_salvar = ordenar_inventario(normalizar_dataframe_inventario(_normalizar_legacy_dataframe(df).fillna("").astype(str)))
    planilha = conectar_google_sheets()
    nome_aba = _nome_aba(unidade)
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"
    sucesso_sheets = False
    if planilha:
        try:
            try:
                aba = planilha.worksheet(nome_aba)
            except gspread.exceptions.WorksheetNotFound:
                aba = planilha.add_worksheet(title=nome_aba, rows=max(100, len(df_salvar) + 10), cols=12)
            aba.batch_clear([f"A1:Z{max(100, aba.row_count)}"])
            aba.resize(rows=max(100, len(df_salvar) + 10), cols=12)
            valores = [COLUNAS_INVENTARIO] + df_salvar[COLUNAS_INVENTARIO].values.tolist()
            aba.update(values=valores, range_name="A1")
            sucesso_sheets = True
        except Exception as e:
            st.error(f"⚠️ Erro ao gravar no Google Sheets: {e}")
    try:
        df_salvar.to_excel(nome_arquivo_local, index=False)
    except Exception as e:
        st.error(f"Erro no backup local: {e}")
    carregar_dados_excel.clear()
    return sucesso_sheets or os.path.exists(nome_arquivo_local)


def registrar_patrimonio(codigo_barras: str, tipo_patrimonio: str, setor: str, unidade: str, fabricante: str = "", numero_patrimonio: str = "") -> bool:
    codigo = _valor_texto(codigo_barras)
    setor = normalizar_setor(_valor_texto(setor))
    tipo = _normalizar_tipo(tipo_patrimonio)
    fabricante = normalizar_fabricante(_valor_texto(fabricante))
    numero = _valor_texto(numero_patrimonio)
    if tipo not in TIPOS_PATRIMONIO or not unidade or not setor or not codigo:
        return False
    df, _ = carregar_dados_excel(unidade)
    df = _normalizar_legacy_dataframe(df)
    if (df["Código de Barras"].astype(str).str.strip().str.casefold() == codigo.casefold()).any():
        st.warning(f"O código de barras `{codigo}` já está cadastrado nesta unidade.")
        return False
    nova = {"Setor": setor, "Tipo de Patrimônio": tipo, "Nº de Patrimônio": numero, "Código de Barras": codigo, "Fabricante": fabricante, "Data Cadastro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Origem": "Sistema de Inventários", "Status": "Ativo"}
    df = pd.concat([df, pd.DataFrame([nova])], ignore_index=True)
    return salvar_no_excel(df, unidade)


def adicionar_e_salvar_sem_sobrescrever(codigo: str, patrimonio: str, setor: str, unidade: str, fabricante: str = "", numero_patrimonio: str = "") -> bool:
    return registrar_patrimonio(codigo, patrimonio, setor, unidade, fabricante, numero_patrimonio)


adicionar_e_salvar = adicionar_e_salvar_sem_sobrescrever


def _aplicar_exclusao_setor(df: pd.DataFrame, setor: str) -> Tuple[pd.DataFrame, bool]:
    df = _normalizar_legacy_dataframe(df)
    if df.empty:
        return df.copy(), False
    setor_normalizado = normalizar_setor(setor).casefold()
    mask = df["Setor"].astype(str).str.strip().str.casefold() == setor_normalizado
    return (df.loc[~mask].copy(), True) if mask.any() else (df.copy(), False)


def _aplicar_exclusao_patrimonio(df: pd.DataFrame, setor: str, coluna: str) -> Tuple[pd.DataFrame, bool]:
    """Remove exatamente uma linha do setor selecionado.

    A interface atual seleciona uma coluna/atributo exibido a partir da primeira
    linha do setor. A implementação anterior usava o valor dessa primeira linha
    como filtro global, podendo apagar vários patrimônios do mesmo tipo. Agora a
    exclusão é feita pelo índice da linha efetivamente selecionada.
    """
    df = _normalizar_legacy_dataframe(df)
    if df.empty:
        return df.copy(), False

    setor_normalizado = normalizar_setor(setor).casefold()
    mask_setor = df["Setor"].astype(str).str.strip().str.casefold() == setor_normalizado
    if not mask_setor.any():
        return df.copy(), False

    subset = df.loc[mask_setor]
    coluna = _valor_texto(coluna)
    colunas_validas = set(COLUNAS_INVENTARIO)
    if coluna not in colunas_validas:
        tipo = _normalizar_tipo(re.sub(r"\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio", "", coluna, flags=re.I))
        if tipo not in TIPOS_PATRIMONIO:
            return df.copy(), False
        coluna = "Tipo de Patrimônio"

    indice_alvo = subset.index[0]
    valor_alvo = _valor_texto(df.at[indice_alvo, coluna])
    if not valor_alvo:
        return df.copy(), False

    mask_excluir = pd.Series(False, index=df.index)
    mask_excluir.loc[indice_alvo] = True
    novo = df.loc[~mask_excluir].copy().reset_index(drop=True)
    return novo, True


def excluir_setor(setor: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    novo, alterado = _aplicar_exclusao_setor(df, setor)
    return salvar_no_excel(novo, unidade) if alterado else False


def excluir_patrimonio(setor: str, coluna: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    novo, alterado = _aplicar_exclusao_patrimonio(df, setor, coluna)
    return salvar_no_excel(novo, unidade) if alterado else False
