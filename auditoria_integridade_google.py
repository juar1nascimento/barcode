from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

COLUNAS_INVENTARIO = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", "Fabricante", "Data Cadastro"]
FORMATO_DATA_HORA = "%d-%m-%Y %H:%M:%S"


def normalizar_data_hora(valor: Any) -> str:
    """Converte datas legadas para DD-MM-YYYY HH:MM:SS."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    if not texto or texto.casefold() in {"nan", "none", "null", "nat"}:
        return ""
    formatos = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    )
    for formato in formatos:
        try:
            return datetime.strptime(texto, formato).strftime(FORMATO_DATA_HORA)
        except ValueError:
            pass
    try:
        return pd.to_datetime(texto, dayfirst=True).to_pydatetime().strftime(FORMATO_DATA_HORA)
    except Exception:
        return texto


def normalizar_dataframe_google(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUNAS_INVENTARIO)
    saida = df.copy().fillna("")
    saida.columns = [str(c).strip() for c in saida.columns]
    for coluna in COLUNAS_INVENTARIO:
        if coluna not in saida.columns:
            saida[coluna] = ""
    saida = saida.reindex(columns=COLUNAS_INVENTARIO).astype(str)
    saida["Data Cadastro"] = saida["Data Cadastro"].map(normalizar_data_hora)
    return saida


def auditar_abas_google(planilha) -> dict:
    """Audita todas as abas reais da planilha, sem alterar dados."""
    relatorio = {
        "abas": [],
        "total_abas": 0,
        "total_linhas": 0,
        "datas_legadas": 0,
        "linhas_sem_data": 0,
        "duplicidades_por_numero": 0,
        "abas_com_problemas": 0,
    }
    if planilha is None:
        return relatorio
    for aba in planilha.worksheets():
        valores = aba.get_all_values()
        linhas = valores[1:] if valores else []
        cabecalho = [str(v).strip() for v in valores[0]] if valores else []
        relatorio["total_abas"] += 1
        relatorio["total_linhas"] += len(linhas)
        problemas = []
        if cabecalho != COLUNAS_INVENTARIO:
            problemas.append("cabecalho fora do schema canonico")
        if valores and len(valores) > 1:
            df = pd.DataFrame(linhas, columns=cabecalho)
            df = normalizar_dataframe_google(df)
            datas_originais = df["Data Cadastro"].map(str)
            # Apos normalizar, compara com a representacao original quando possivel.
            coluna_data_idx = cabecalho.index("Data Cadastro") if "Data Cadastro" in cabecalho else None
            if coluna_data_idx is None:
                relatorio["linhas_sem_data"] += len(df)
            else:
                originais = [str(l[coluna_data_idx]).strip() if len(l) > coluna_data_idx else "" for l in linhas]
                for original, normalizado in zip(originais, datas_originais):
                    if not original:
                        relatorio["linhas_sem_data"] += 1
                    elif original != normalizado:
                        relatorio["datas_legadas"] += 1
            duplicadas = int(df.duplicated(subset=["Nº de Patrimônio"], keep=False).sum())
            relatorio["duplicidades_por_numero"] += duplicadas
            if duplicadas:
                problemas.append("numero de patrimonio duplicado")
        if problemas:
            relatorio["abas_com_problemas"] += 1
        relatorio["abas"].append({"aba": aba.title, "linhas": len(linhas), "problemas": problemas})
    return relatorio


def corrigir_datas_em_aba(aba) -> int:
    """Corrige somente a coluna Data Cadastro da aba e devolve qtd alterada."""
    valores = aba.get_all_values()
    if not valores:
        return 0
    cabecalho = [str(v).strip() for v in valores[0]]
    if "Data Cadastro" not in cabecalho:
        return 0
    idx = cabecalho.index("Data Cadastro")
    alteradas = 0
    novas = [list(linha) for linha in valores]
    for pos, linha in enumerate(novas[1:], start=1):
        while len(linha) <= idx:
            linha.append("")
        original = str(linha[idx]).strip()
        normalizada = normalizar_data_hora(original)
        if normalizada != original:
            linha[idx] = normalizada
            alteradas += 1
    if alteradas:
        aba.update(values=novas, range_name=f"A1:{chr(65 + min(len(cabecalho), 26) - 1)}{len(novas)}")
    return alteradas
