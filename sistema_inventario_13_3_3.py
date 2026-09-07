def adicionar_e_salvar_sem_sobrescrever(
    codigo: str, patrimonio: str, setor: str, unidade: str, fabricante: str = ""
) -> bool:
    setor_limpo = setor.strip()
    codigo_limpo = codigo.strip()
    fabricante_limpo = fabricante.strip()
    
    patrimonio_cabecalho = formatar_nome_patrimonio(patrimonio.strip())
    coluna_fabricante = formatar_nome_fabricante(patrimonio.strip())

    if not setor_limpo or not codigo_limpo or not patrimonio_cabecalho or not unidade:
        return False

    # Obtém os dados atualizados diretamente do Google Sheets/Excel
    df_atual, _ = carregar_dados_excel(unidade)
    df = df_atual.copy()

    if df.empty or COLUNA_CHAVE not in df.columns:
        df = pd.DataFrame(columns=[COLUNA_CHAVE])

    if patrimonio_cabecalho not in df.columns: 
        df[patrimonio_cabecalho] = ""
    if coluna_fabricante not in df.columns: 
        df[coluna_fabricante] = ""

    df = df.fillna("").astype(str)
    
    # Procura por linhas existentes do mesmo setor
    mask_setor = df[COLUNA_CHAVE].str.strip().str.lower() == setor_limpo.lower()
    indices_setor = df[mask_setor].index

    linha_destino_idx = None
    for idx in indices_setor:
        val_celula = str(df.at[idx, patrimonio_cabecalho]).strip().lower()
        if val_celula in ["", "nan", "none", "<na>", "null"]:
            linha_destino_idx = idx
            break

    # Se já existir o setor com o espaço do patrimônio vazio, preenche
    if linha_destino_idx is not None:
        df.at[linha_destino_idx, patrimonio_cabecalho] = codigo_limpo
        if fabricante_limpo: 
            df.at[linha_destino_idx, coluna_fabricante] = fabricante_limpo
    else:
        # Se não houver linha livre para esse setor, adiciona uma nova mantendo a integridade
        nova_linha = {col: "" for col in df.columns}
        nova_linha[COLUNA_CHAVE] = setor_limpo
        nova_linha[patrimonio_cabecalho] = codigo_limpo
        nova_linha[coluna_fabricante] = fabricante_limpo
        df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)

    sucesso = salvar_no_excel(df, unidade)
    return sucesso