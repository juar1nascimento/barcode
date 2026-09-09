"""Camada de persistência do inventário.

Responsável por leitura/escrita em Google Sheets e no backup Excel local.
Não importa Streamlit: mensagens de interface e cache ficam na camada de aplicação.
"""

import os
import re
from datetime import datetime
from typing import Optional, Tuple

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from inventario_regras import (
    TIPOS_PATRIMONIO_OFICIAIS,
    normalizar_dataframe_inventario,
    normalizar_fabricante,
    normalizar_setor,
    ordenar_inventario,
)

ARQUIVO_EXCEL = "inventario_dados.xlsx"
COLUNAS_INVENTARIO = [
    "Setor",
    "Tipo de Patrimônio",
    "Nº de Patrimônio",
    "Código de Barras",
    "Fabricante",
    "Data Cadastro",
    "Origem",
    "Status",
]
TIPOS_PATRIMONIO = TIPOS_PATRIMONIO_OFICIAIS


def _valor_texto(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if re.fullmatch(r"-?\d+\.0", s):
        s = s[:-2]
    return s


def normalizar_tipo(valor: str) -> str:
    valor = re.sub(r"\s+", " ", _valor_texto(valor))
    mapa = {
        "computador": "CPU",
        "cpu": "CPU",
        "monitor": "Monitores",
        "monitores": "Monitores",
        "teclado": "Teclado",
        "mouse": "Mouse",
        "impressora": "Imprenssoras",
        "impressoras": "Imprenssoras",
    }
    return mapa.get(valor.casefold(), valor if valor in TIPOS_PATRIMONIO else "Outros Dispositivos")


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


def normalizar_legacy_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUNAS_INVENTARIO)
    df = df.fillna("").copy()
    df.columns = [str(c).strip() for c in df.columns]
    if "Tipo de Patrimônio" in df.columns and "Código de Barras" in df.columns:
        resultado = df.reindex(columns=COLUNAS_INVENTARIO, fill_value="").fillna("").astype(str)
        return ordenar_inventario(normalizar_dataframe_inventario(resultado))

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
            registros.append({
                "Setor": setor,
                "Tipo de Patrimônio": tipo,
                "Nº de Patrimônio": valor,
                "Código de Barras": "",
                "Fabricante": fabricante,
                "Data Cadastro": "",
                "Origem": "Migração do formato anterior",
                "Status": "Ativo",
            })
    resultado = pd.DataFrame(registros, columns=COLUNAS_INVENTARIO).fillna("").astype(str)
    return ordenar_inventario(resultado)


def _normalizar_unidade_aba(nome: str) -> str:
    aliases = {
        "URS Jacara_pe": "URS Jacaraípe",
        "UBS Bairro de F_tima": "UBS Bairro de Fátima",
    }
    return aliases.get(_valor_texto(nome), _valor_texto(nome))


def _nome_aba(unidade: str) -> str:
    return _normalizar_unidade_aba(unidade)[:90].strip()


def _nome_arquivo_local(unidade: str) -> str:
    return f"Inventario_{re.sub(r'[^a-zA-Z0-9_]', '_', _normalizar_unidade_aba(unidade))}.xlsx"


def conectar_google_sheets(secrets=None):
    """Abre a planilha configurada; retorna None quando não há configuração."""
    try:
        if secrets is None:
            return None
        if "connections" in secrets and "gsheets" in secrets["connections"]:
            sec = secrets["connections"]["gsheets"]
        elif "gcp_service_account" in secrets:
            sec = secrets["gcp_service_account"]
        else:
            return None
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        campos = (
            "type", "project_id", "private_key_id", "private_key", "client_email",
            "client_id", "auth_uri", "token_uri", "auth_provider_x509_cert_url",
            "client_x509_cert_url",
        )
        creds_dict = {k: sec.get(k) for k in campos}
        creds_dict["type"] = creds_dict.get("type") or "service_account"
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet_url = sec.get("spreadsheet") or secrets.get("spreadsheet_url")
        return client.open_by_url(sheet_url) if sheet_url else None
    except Exception:
        return None


def carregar_dados(unidade: str, secrets=None) -> Tuple[pd.DataFrame, str]:
    unidade = _normalizar_unidade_aba(unidade)
    planilha = conectar_google_sheets(secrets)
    nome_aba = _nome_aba(unidade)
    nome_arquivo_local = _nome_arquivo_local(unidade)
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
                    partes.append(normalizar_legacy_dataframe(pd.DataFrame(valores[1:], columns=valores[0])))
                    fontes.append(nome)
            if partes:
                combinado = pd.concat(partes, ignore_index=True)
                combinado = normalizar_legacy_dataframe(combinado).drop_duplicates(
                    subset=["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Código de Barras"],
                    keep="first",
                )
                return ordenar_inventario(combinado.reindex(columns=COLUNAS_INVENTARIO, fill_value="")), f"Google Sheets ({' + '.join(fontes)})"
            return pd.DataFrame(columns=COLUNAS_INVENTARIO), f"Google Sheets ({nome_aba})"
        except Exception:
            pass
    if os.path.exists(nome_arquivo_local):
        try:
            return normalizar_legacy_dataframe(pd.read_excel(nome_arquivo_local, dtype=str)), nome_arquivo_local
        except Exception:
            pass
    return pd.DataFrame(columns=COLUNAS_INVENTARIO), nome_arquivo_local


def salvar_dados(df: pd.DataFrame, unidade: str, secrets=None) -> bool:
    unidade = _normalizar_unidade_aba(unidade)
    df_salvar = ordenar_inventario(
        normalizar_dataframe_inventario(normalizar_legacy_dataframe(df).fillna("").astype(str))
    )
    planilha = conectar_google_sheets(secrets)
    nome_aba = _nome_aba(unidade)
    nome_arquivo_local = _nome_arquivo_local(unidade)
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
        except Exception:
            pass
    try:
        df_salvar.to_excel(nome_arquivo_local, index=False)
    except Exception:
        pass
    return sucesso_sheets or os.path.exists(nome_arquivo_local)


def registrar_patrimonio(codigo_barras: str, tipo_patrimonio: str, setor: str, unidade: str,
                         fabricante: str = "", numero_patrimonio: str = "", secrets=None) -> bool:
    codigo = _valor_texto(codigo_barras)
    setor = normalizar_setor(_valor_texto(setor))
    tipo = normalizar_tipo(tipo_patrimonio)
    fabricante = normalizar_fabricante(_valor_texto(fabricante))
    numero = _valor_texto(numero_patrimonio)
    if tipo not in TIPOS_PATRIMONIO or not unidade or not setor or not codigo:
        return False
    df, _ = carregar_dados(unidade, secrets)
    if (df["Código de Barras"].astype(str).str.strip().str.casefold() == codigo.casefold()).any():
        return False
    nova = {
        "Setor": setor,
        "Tipo de Patrimônio": tipo,
        "Nº de Patrimônio": numero,
        "Código de Barras": codigo,
        "Fabricante": fabricante,
        "Data Cadastro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Origem": "Sistema de Inventários",
        "Status": "Ativo",
    }
    return salvar_dados(pd.concat([df, pd.DataFrame([nova])], ignore_index=True), unidade, secrets)


__all__ = [
    "ARQUIVO_EXCEL",
    "COLUNAS_INVENTARIO",
    "TIPOS_PATRIMONIO",
    "_valor_texto",
    "normalizar_tipo",
    "normalizar_legacy_dataframe",
    "conectar_google_sheets",
    "carregar_dados",
    "salvar_dados",
    "registrar_patrimonio",
]
