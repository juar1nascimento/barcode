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


def _remover_transferencia_do_destino(df: pd.DataFrame, equipamento: pd.Series) -> pd.DataFrame:
    """Remove somente a linha criada pela transferência, para tentativa de rollback."""
    codigo = str(equipamento.get("Código de Barras", "")).strip().casefold()
    patrimonio = str(equipamento.get("Nº de Patrimônio", "")).strip().casefold()
    mascara = df["Código de Barras"].astype(str).str.strip().str.casefold().eq(codigo)
    if patrimonio:
        mascara = mascara | df["Nº de Patrimônio"].astype(str).str.strip().str.casefold().eq(patrimonio)
    if mascara.any():
        return df.drop(index=df.index[mascara][0]).reset_index(drop=True)
    return df


def registrar_saida(codigo_barras: str, unidade: str, motivo: str, destino: str = "", observacoes: str = "") -> tuple[bool, str]:
    codigo = _valor_texto(codigo_barras)
    unidade = _valor_texto(unidade)
    motivo = _valor_texto(motivo)
    destino_limpo = _valor_texto(destino)
    eh_transferencia = "transferência" in motivo.casefold()

    if not unidade:
        return False, "Selecione a unidade de origem."
    if not codigo:
        return False, "Informe ou bipe o código do equipamento."
    if not motivo:
        return False, "Informe o motivo da saída."
    if eh_transferencia and not destino_limpo:
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

    if eh_transferencia:
        df_destino = _carregar(destino_limpo)
        codigo_equipamento = equipamento["Código de Barras"].strip().casefold()
        if (df_destino["Código de Barras"].str.strip().str.casefold() == codigo_equipamento).any():
            return False, f"O equipamento `{equipamento['Código de Barras']}` já existe na unidade de destino `{destino_limpo}`."

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        nova_linha = equipamento.to_dict()
        nova_linha["Status"] = "Ativo"
        nova_linha["Data Cadastro"] = agora
        nova_linha["Origem"] = f"Transferência recebida de {unidade}"
        df_destino_novo = pd.concat([df_destino, pd.DataFrame([nova_linha])], ignore_index=True)

        # A operação é tratada como uma transação de duas etapas: primeiro confirma
        # a entrada no destino; se a origem falhar, tenta remover a linha recém-criada.
        if not salvar_no_excel(df_destino_novo, destino_limpo):
            return False, "Não foi possível persistir o equipamento na unidade de destino. A unidade de origem não foi alterada."

        df_origem_novo = df_origem.copy()
        df_origem_novo.at[idx, "Status"] = "Transferido"
        df_origem_novo.at[idx, "Origem"] = f"Transferido para {destino_limpo}" + (f" | Observação: {observacoes.strip()}" if observacoes.strip() else "")
        if salvar_no_excel(df_origem_novo, unidade):
            return True, f"Transferência registrada: **{unidade}** → **{destino_limpo}**."

        # Melhor esforço de rollback: evita deixar dois registros ativos quando
        # a gravação da origem falha depois da gravação do destino.
        rollback_df = _remover_transferencia_do_destino(df_destino_novo, equipamento)
        if salvar_no_excel(rollback_df, destino_limpo):
            return False, "A transferência não foi concluída: a atualização da origem falhou e a entrada criada no destino foi revertida. Nenhuma unidade deve ser repetida sem nova conferência."
        return False, "Falha crítica na transferência: a origem não foi atualizada e o rollback do destino também falhou. Não repita a operação; confira as duas unidades antes de qualquer nova tentativa."

    status = "Baixado" if "baixa" in motivo.casefold() or "desfazimento" in motivo.casefold() else "Em movimentação"
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
