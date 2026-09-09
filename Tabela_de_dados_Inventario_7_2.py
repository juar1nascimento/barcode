import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

ARQUIVO_EXCEL = "inventario_dados.xlsx"
COLUNA_CHAVE = "Setor"
COLUNAS_OBSOLETAS = ["Data_Hora", "Usuario", "Código de Barras", "Origem", "Status"]
TIPOS_PATRIMONIO = ("CPU", "Monitores", "Teclado", "Mouse", "Imprenssoras", "Outros Dispositivos")
# Schema definitivo: as colunas Código de Barras, Origem e Status não são persistidas.
# O valor lido pelo scanner passa a ser gravado em Nº de Patrimônio.
COLUNAS_INVENTARIO = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Fabricante", "Data Cadastro"]
COLUNAS_PADRAO = COLUNAS_INVENTARIO.copy()
SETORES_PADRAO = ["Consultório", "Almoxarifado", "Farmacia", "Sala de Preparo", "Sala de Vacina", "Sala de curativo", "Gerencia", "Administração", "Odontologia", "Recepção", "Outro Setor"]
LISTA_URS_PADRAO = ["URS Novo Horizonte", "URS Jacaraípe", "URS Boa Vista", "URS Feu Rosa", "URS Serra Sede", "URS Serra Dourada"]
LISTA_UBS_PADRAO = ["UBS André Carloni", "UBS Bairro de Fátima", "UBS Feu Rosa", "UBS Barcelona", "UBS Barro Branco", "UBS Campinho da Serra", "UBS Carapebus", "UBS Carapina Grande", "UBS Central Carapina", "UBS Cidade Continental", "UBS Eldorado", "UBS Jardim Carapina", "UBS Jardim Tropical", "UBS José de Anchieta", "UBS Laranjeiras Velha", "UBS Manguinhos", "UBS Manoel Plaza", "UBS Nova Almeida", "UBS Nova Carapina I", "UBS Nova Carapina II", "UBS Oceania", "UBS Pitanga", "UBS Planalto Serrano (Bloco A)", "UBS Planalto Serrano (Bloco B)", "UBS Porto Canoa", "UBS São Diogo", "UBS São Marcos", "UBS Taquara I", "UBS Taquara II", "UBS Vila Nova de Colares", "UBS Vista da Serra", "UBS Itinerante (atendimento na UBS)"]
UNIDADES_PADRAO = LISTA_URS_PADRAO + LISTA_UBS_PADRAO

FUSO_HORARIO_APLICACAO = ZoneInfo("America/Sao_Paulo")


def _agora_brasilia() -> datetime:
    """Retorna a data/hora oficial do cadastro no fuso de Brasília."""
    return datetime.now(FUSO_HORARIO_APLICACAO)


def _data_hora_cadastro() -> str:
    """Formata o instante do cadastro de forma estável e auditável."""
    return _agora_brasilia().strftime("%Y-%m-%d %H:%M:%S")


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

    # Formato definitivo já normalizado.
    if "Tipo de Patrimônio" in df.columns and "Nº de Patrimônio" in df.columns:
        saida = df.reindex(columns=COLUNAS_INVENTARIO, fill_value="").fillna("").astype(str)
        return saida

    # Formato anterior: cada tipo era uma coluna e o código bipado ficava nela.
    setor_col = "Setor" if "Setor" in df.columns else (df.columns[0] if len(df.columns) else "Setor")
    registros = []
    for _, row in df.iterrows():
        setor = _valor_texto(row.get(setor_col, ""))
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
                    fabricante = _valor_texto(row.get(c2, ""))
                    break
            registros.append({
                "Setor": setor,
                "Tipo de Patrimônio": tipo,
                "Nº de Patrimônio": valor,
                "Fabricante": fabricante,
                "Data Cadastro": "",
            })
    return pd.DataFrame(registros, columns=COLUNAS_INVENTARIO).fillna("").astype(str)


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
                combinado = pd.concat(partes, ignore_index=True).drop_duplicates(subset=["Setor", "Tipo de Patrimônio", "Nº de Patrimônio"], keep="first")
                return combinado.reindex(columns=COLUNAS_INVENTARIO, fill_value=""), f"Google Sheets ({' + '.join(fontes)})"
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
    df_salvar = _normalizar_legacy_dataframe(df).fillna("").astype(str)
    planilha = conectar_google_sheets()
    nome_aba = _nome_aba(unidade)
    nome_arquivo_local = f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', unidade)}.xlsx"
    sucesso_sheets = False
    if planilha:
        try:
            try:
                aba = planilha.worksheet(nome_aba)
            except gspread.exceptions.WorksheetNotFound:
                aba = planilha.add_worksheet(title=nome_aba, rows=max(100, len(df_salvar) + 10), cols=8)
            aba.batch_clear([f"A1:Z{max(100, aba.row_count)}"])
            aba.resize(rows=max(100, len(df_salvar) + 10), cols=max(8, len(COLUNAS_INVENTARIO)))
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
    setor = _valor_texto(setor)
    tipo = _normalizar_tipo(tipo_patrimonio)
    fabricante = _valor_texto(fabricante)
    numero = _valor_texto(numero_patrimonio) or codigo
    if tipo not in TIPOS_PATRIMONIO or not unidade or not setor or not codigo:
        return False
    df, _ = carregar_dados_excel(unidade)
    df = _normalizar_legacy_dataframe(df)
    if (df["Nº de Patrimônio"].astype(str).str.strip() == numero).any():
        st.warning(f"O número de patrimônio `{numero}` já está cadastrado nesta unidade.")
        return False
    nova = {
        "Setor": setor,
        "Tipo de Patrimônio": tipo,
        "Nº de Patrimônio": numero,
        "Fabricante": fabricante,
        "Data Cadastro": _data_hora_cadastro(),
    }
    df = pd.concat([df, pd.DataFrame([nova])], ignore_index=True)
    return salvar_no_excel(df, unidade)


def adicionar_e_salvar_sem_sobrescrever(codigo: str, patrimonio: str, setor: str, unidade: str, fabricante: str = "", numero_patrimonio: str = "") -> bool:
    return registrar_patrimonio(codigo, patrimonio, setor, unidade, fabricante, numero_patrimonio)


adicionar_e_salvar = adicionar_e_salvar_sem_sobrescrever


def _aplicar_exclusao_setor(df: pd.DataFrame, setor: str) -> Tuple[pd.DataFrame, bool]:
    df = _normalizar_legacy_dataframe(df)
    if df.empty:
        return df.copy(), False
    mask = df["Setor"].astype(str).str.strip().str.casefold() == _valor_texto(setor).casefold()
    return (df.loc[~mask].copy(), True) if mask.any() else (df.copy(), False)


def _aplicar_exclusao_patrimonio(df: pd.DataFrame, setor: str, coluna: str) -> Tuple[pd.DataFrame, bool]:
    df = _normalizar_legacy_dataframe(df)
    if df.empty:
        return df.copy(), False
    mask_setor = df["Setor"].astype(str).str.strip().str.casefold() == _valor_texto(setor).casefold()
    if not mask_setor.any():
        return df.copy(), False
    subset = df.loc[mask_setor].copy()
    coluna = str(coluna or "").strip()
    if coluna == "Tipo de Patrimônio":
        valor = _valor_texto(subset.iloc[0]["Tipo de Patrimônio"])
        mask_excluir = mask_setor & df["Tipo de Patrimônio"].astype(str).eq(valor)
    elif coluna == "Nº de Patrimônio":
        valor = _valor_texto(subset.iloc[0]["Nº de Patrimônio"])
        mask_excluir = mask_setor & df["Nº de Patrimônio"].astype(str).str.strip().eq(valor)
    else:
        tipo = _normalizar_tipo(re.sub(r"\s*-\s*N[ºo]?\s*de\s*Patrim[ôo]nio", "", coluna, flags=re.I))
        mask_excluir = mask_setor & df["Tipo de Patrimônio"].astype(str).eq(tipo)
    return (df.loc[~mask_excluir].copy(), True) if mask_excluir.any() else (df.copy(), False)


def excluir_setor(setor: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    novo, alterado = _aplicar_exclusao_setor(df, setor)
    if not alterado:
        return False
    return salvar_no_excel(novo, unidade)


def excluir_patrimonio(setor: str, coluna: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    novo, alterado = _aplicar_exclusao_patrimonio(df, setor, coluna)
    if not alterado:
        return False
    return salvar_no_excel(novo, unidade)
