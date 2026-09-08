import pandas as pd
from datetime import date, datetime

from Tabela_de_dados_Inventario_7_2 import carregar_dados_excel, salvar_no_excel, _normalizar_tipo, _valor_texto, COLUNAS_INVENTARIO
from inventario_regras import normalizar_setor, normalizar_fabricante


def _carregar(unidade: str) -> pd.DataFrame:
    df, _ = carregar_dados_excel(unidade)
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUNAS_INVENTARIO)
    return df.reindex(columns=COLUNAS_INVENTARIO, fill_value="").fillna("").astype(str)


def registrar_entrada(codigo_barras: str, tipo_equipamento: str, unidade: str, setor: str,
                      numero_patrimonio: str = "", fabricante: str = "", setor_origem: str = "",
                      data_recebimento: date | datetime | None = None) -> tuple[bool, str]:
    codigo = _valor_texto(codigo_barras)
    unidade = _valor_texto(unidade)
    setor = normalizar_setor(_valor_texto(setor))
    numero = _valor_texto(numero_patrimonio)
    fabricante = normalizar_fabricante(_valor_texto(fabricante))
    tipo = _normalizar_tipo(tipo_equipamento)

    if not unidade:
        return False, "Selecione a unidade de destino."
    if not setor:
        return False, "Informe o setor de destino."
    if not codigo:
        return False, "Informe ou bipe o código do equipamento."

    df = _carregar(unidade)
    if (df["Código de Barras"].str.strip().str.casefold() == codigo.casefold()).any():
        return False, f"O código de barras `{codigo}` já está cadastrado nesta unidade."

    if isinstance(data_recebimento, datetime):
        data_cadastro = data_recebimento.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(data_recebimento, date):
        data_cadastro = datetime.combine(data_recebimento, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
    else:
        data_cadastro = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    origem = f"Entrada de equipamentos{(' - origem: ' + setor_origem) if setor_origem else ''}"
    nova = {
        "Setor": setor,
        "Tipo de Patrimônio": tipo,
        "Nº de Patrimônio": numero or codigo,
        "Código de Barras": codigo,
        "Fabricante": fabricante,
        "Data Cadastro": data_cadastro,
        "Origem": origem,
        "Status": "Ativo",
    }
    novo_df = pd.concat([df, pd.DataFrame([nova])], ignore_index=True)
    return (True, "Entrada registrada com sucesso.") if salvar_no_excel(novo_df, unidade) else (False, "Não foi possível persistir a entrada no armazenamento.")


def registrar_saida(codigo_barras: str, unidade: str, motivo: str, destino: str = "", observacoes: str = "") -> tuple[bool, str]:
    codigo = _valor_texto(codigo_barras)
    unidade = _valor_texto(unidade)
    motivo = _valor_texto(motivo)
    destino_limpo = _valor_texto(destino)
    if not unidade:
        return False, "Selecione a unidade de origem."
    if not codigo:
        return False, "Informe ou bipe o código do equipamento."
    if not motivo:
        return False, "Informe o motivo da saída."
    if "Transferência" in motivo and not destino_limpo:
        return False, "Informe a unidade de destino da transferência."
    if destino_limpo.casefold() == unidade.casefold():
        return False, "A unidade de destino deve ser diferente da unidade de origem."

    df_origem = _carregar(unidade)
    mask = df_origem["Código de Barras"].str.strip().str.casefold() == codigo.casefold()
    if not mask.any():
        mask = df_origem["Nº de Patrimônio"].str.strip().str.casefold() == codigo.casefold()
    if not mask.any():
        return False, f"Nenhum equipamento com o código/patrimônio `{codigo}` foi encontrado em `{unidade}`."

    idx = df_origem.index[mask][0]
    equipamento = df_origem.loc[idx].copy()

    if "Transferência" in motivo:
        df_destino = _carregar(destino_limpo)
        if (df_destino["Código de Barras"].str.strip().str.casefold() == equipamento["Código de Barras"].strip().casefold()).any():
            return False, f"O equipamento `{equipamento['Código de Barras']}` já existe na unidade de destino `{destino_limpo}`."

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        nova_linha = equipamento.to_dict()
        nova_linha["Status"] = "Ativo"
        nova_linha["Data Cadastro"] = agora
        nova_linha["Origem"] = f"Transferência recebida de {unidade}"
        df_destino = pd.concat([df_destino, pd.DataFrame([nova_linha])], ignore_index=True)

        if not salvar_no_excel(df_destino, destino_limpo):
            return False, "Não foi possível persistir o equipamento na unidade de destino."

        df_origem.at[idx, "Status"] = "Transferido"
        df_origem.at[idx, "Origem"] = f"Transferido para {destino_limpo}" + (f" | Observação: {observacoes.strip()}" if observacoes.strip() else "")
        if not salvar_no_excel(df_origem, unidade):
            return False, "O equipamento foi gravado no destino, mas a atualização da unidade de origem falhou. Verifique o inventário de origem antes de repetir a transferência."
        return True, f"Transferência registrada: **{unidade}** → **{destino_limpo}**."

    status = "Baixado" if "Baixa" in motivo or "Desfazimento" in motivo else "Em movimentação"
    detalhe = motivo + (f" | Destino: {destino_limpo}" if destino_limpo else "")
    if observacoes.strip():
        detalhe += f" | Observação: {observacoes.strip()}"
    df_origem.at[idx, "Status"] = status
    df_origem.at[idx, "Origem"] = detalhe
    ok = salvar_no_excel(df_origem, unidade)
    if not ok:
        return False, "A movimentação não pôde ser persistida."
    return True, f"Saída registrada. Status do equipamento: **{status}**."


def excluir_patrimonio_exato(setor: str, tipo_patrimonio: str, valor_patrimonio: str, unidade: str) -> tuple[bool, str]:
    """Exclui somente o registro cujo setor, tipo e valor foram selecionados."""
    setor_alvo = normalizar_setor(_valor_texto(setor))
    tipo_alvo = _normalizar_tipo(_valor_texto(tipo_patrimonio))
    valor_alvo = _valor_texto(valor_patrimonio)
    if not unidade or not setor_alvo or not tipo_alvo or not valor_alvo:
        return False, "Os dados do patrimônio selecionado estão incompletos."
    df = _carregar(unidade)
    if df.empty:
        return False, "Nenhum patrimônio foi encontrado nesta unidade."
    mascara = (
        df["Setor"].map(normalizar_setor).str.casefold().eq(setor_alvo.casefold())
        & df["Tipo de Patrimônio"].astype(str).str.strip().eq(tipo_alvo)
        & df["Nº de Patrimônio"].astype(str).str.strip().eq(valor_alvo)
    )
    if not mascara.any():
        mascara = (
            df["Setor"].map(normalizar_setor).str.casefold().eq(setor_alvo.casefold())
            & df["Tipo de Patrimônio"].astype(str).str.strip().eq(tipo_alvo)
            & df["Código de Barras"].astype(str).str.strip().eq(valor_alvo)
        )
    if not mascara.any():
        return False, f"O patrimônio `{valor_alvo}` não foi encontrado no setor `{setor_alvo}`."
    indice = df.index[mascara][0]
    novo_df = df.drop(index=indice).reset_index(drop=True)
    if not salvar_no_excel(novo_df, unidade):
        return False, "Não foi possível persistir a exclusão do patrimônio."
    return True, "Patrimônio excluído com sucesso."
