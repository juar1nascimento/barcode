from pathlib import Path
import re


def patch_backend():
    path = Path('Tabela_de_dados_Inventario_7_2.py')
    text = path.read_text(encoding='utf-8')
    replacement = '''def _aplicar_exclusao_setor(df: pd.DataFrame, setor: str) -> tuple[pd.DataFrame, bool]:
    """Aplica a exclusão de setor em memória e informa se houve alteração."""
    if df.empty or COLUNA_CHAVE not in df.columns:
        return df.copy(), False
    setor_limpo = str(setor or "").strip().casefold()
    if not setor_limpo:
        return df.copy(), False
    valores_setor = df[COLUNA_CHAVE].astype(str).str.strip().str.casefold()
    mask_excluir = valores_setor == setor_limpo
    if not mask_excluir.any():
        return df.copy(), False
    return df.loc[~mask_excluir].copy(), True


def _aplicar_exclusao_patrimonio(df: pd.DataFrame, setor: str, coluna: str) -> tuple[pd.DataFrame, bool]:
    """Limpa patrimônio + fabricante somente no setor escolhido."""
    if df.empty or COLUNA_CHAVE not in df.columns or coluna not in df.columns:
        return df.copy(), False
    df_trabalho = df.fillna("").astype(str).copy()
    setor_limpo = str(setor or "").strip().casefold()
    coluna_limpa = str(coluna or "").strip()
    if not setor_limpo or not coluna_limpa:
        return df_trabalho, False
    mask_setor = df_trabalho[COLUNA_CHAVE].str.strip().str.casefold() == setor_limpo
    if not mask_setor.any():
        return df_trabalho, False
    coluna_fabricante = formatar_nome_fabricante(coluna_limpa)
    df_trabalho.loc[mask_setor, coluna_limpa] = ""
    if coluna_fabricante in df_trabalho.columns:
        df_trabalho.loc[mask_setor, coluna_fabricante] = ""
    cols_dados = [c for c in df_trabalho.columns if c != COLUNA_CHAVE]
    if cols_dados:
        mask_linha_vazia = df_trabalho[cols_dados].apply(
            lambda row: all(str(v).strip().lower() in {"", "nan", "none", "null", "<na>"} for v in row),
            axis=1,
        )
        df_trabalho = df_trabalho.loc[~mask_linha_vazia].copy()
    return df_trabalho, True


def excluir_setor(setor: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    df_filtrado, alterado = _aplicar_exclusao_setor(df, setor)
    if not alterado:
        return False
    return salvar_no_excel(df_filtrado, unidade)


def excluir_patrimonio(setor: str, coluna: str, unidade: str) -> bool:
    df, _ = carregar_dados_excel(unidade)
    df_filtrado, alterado = _aplicar_exclusao_patrimonio(df, setor, coluna)
    if not alterado:
        return False
    return salvar_no_excel(df_filtrado, unidade)
'''
    pattern = re.compile(r'def excluir_setor\(setor: str, unidade: str\) -> bool:.*\Z', re.DOTALL)
    text, count = pattern.subn(lambda _: replacement, text, count=1)
    if count != 1:
        raise SystemExit('Funcoes de exclusao do backend nao foram localizadas.')
    path.write_text(text, encoding='utf-8')


def patch_ui():
    path = Path('sistema_inventario.py')
    text = path.read_text(encoding='utf-8')
    replacement = '''        st.session_state.setdefault("gerenciador_exclusao_aberto", False)
        st.session_state.setdefault("tipo_operacao_exclusao", "Excluir Patrimônio")
        st.session_state.setdefault("del_setor", None)
        st.session_state.setdefault("del_setor_patrimonio", None)
        st.session_state.setdefault("del_coluna_patrimonio", None)

        with st.expander(
            f"🗑️ Gerenciador de Exclusão — Aba ({unidade})",
            expanded=st.session_state.get("gerenciador_exclusao_aberto", False),
        ):
            lista_setores_existentes = sorted(
                dict.fromkeys(
                    str(s).strip()
                    for s in df_atual[COLUNA_CHAVE].tolist()
                    if str(s).strip()
                ),
                key=str.casefold,
            )

            st.caption("Selecione a operação. Após uma exclusão, o gerenciador permanece aberto e preserva o setor selecionado quando ele ainda existir.")
            tipo_operacao = st.radio(
                "Operação de exclusão:",
                ["Excluir Setor", "Excluir Patrimônio"],
                horizontal=True,
                key="tipo_operacao_exclusao",
            )

            if not lista_setores_existentes:
                st.info("ℹ️ Não existem setores cadastrados para exclusão nesta unidade.")
            elif tipo_operacao == "Excluir Setor":
                setor_para_excluir = st.selectbox(
                    "Selecione o Setor para apagar inteiramente:",
                    lista_setores_existentes,
                    index=None,
                    key="del_setor",
                    placeholder="Selecione um setor...",
                )
                if setor_para_excluir:
                    st.warning(f"⚠️ A exclusão removerá todas as informações do setor **{setor_para_excluir}** nesta unidade.")

                if setor_para_excluir and st.button(
                    f"🔥 Confirmar Exclusão do Setor '{setor_para_excluir}'",
                    type="primary",
                    use_container_width=True,
                    key="btn_excluir_setor",
                ):
                    sucesso = excluir_setor(setor_para_excluir, unidade)
                    carregar_dados_excel.clear()
                    if sucesso:
                        st.session_state.mensagem_sucesso = f"🗑️ Setor '{setor_para_excluir}' excluído com sucesso."
                        st.session_state.gerenciador_exclusao_aberto = True
                        st.session_state.del_setor = None
                        st.session_state.del_setor_patrimonio = None
                        st.session_state.del_coluna_patrimonio = None
                    else:
                        st.session_state.mensagem_sucesso = f"⚠️ Nenhum registro foi excluído para o setor '{setor_para_excluir}'."
                        st.session_state.gerenciador_exclusao_aberto = True
                    st.rerun()

            else:
                setor_patrimonio_del = st.selectbox(
                    "Selecione o Setor:",
                    lista_setores_existentes,
                    index=None,
                    key="del_setor_patrimonio",
                    placeholder="Selecione um setor...",
                )

                colunas_com_dados, valores_map = [], {}
                if setor_patrimonio_del:
                    linha_setor_df = df_atual[
                        df_atual[COLUNA_CHAVE].astype(str).str.strip().str.casefold()
                        == str(setor_patrimonio_del).strip().casefold()
                    ]
                    if not linha_setor_df.empty:
                        for col in df_atual.columns:
                            if col == COLUNA_CHAVE or col in COLUNAS_OBSOLETAS or str(col).startswith("Fabricante "):
                                continue
                            val = str(linha_setor_df.iloc[0][col]).strip()
                            if val and val.lower() not in {"nan", "none", "null", "<na>"}:
                                colunas_com_dados.append(col)
                                valores_map[col] = val

                colunas_com_dados = sorted(colunas_com_dados, key=str.casefold)
                coluna_patrimonio_del = st.selectbox(
                    "Selecione o Patrimônio:",
                    options=colunas_com_dados,
                    index=None,
                    key="del_coluna_patrimonio",
                    placeholder="Selecione o patrimônio...",
                    format_func=lambda c: f"{c} (Código: {valores_map.get(c, '')})",
                ) if colunas_com_dados else None

                if setor_patrimonio_del and not colunas_com_dados:
                    st.info("ℹ️ O setor selecionado não possui patrimônio preenchido para exclusão.")
                elif coluna_patrimonio_del:
                    st.warning(
                        f"⚠️ Será removido o patrimônio **{coluna_patrimonio_del}** do setor **{setor_patrimonio_del}** e, quando existir, o fabricante correspondente."
                    )

                if coluna_patrimonio_del and setor_patrimonio_del and st.button(
                    f"🗑️ Confirmar Exclusão de '{coluna_patrimonio_del}'",
                    type="secondary",
                    use_container_width=True,
                    key="btn_excluir_patrimonio",
                ):
                    sucesso = excluir_patrimonio(setor_patrimonio_del, coluna_patrimonio_del, unidade)
                    carregar_dados_excel.clear()
                    if sucesso:
                        st.session_state.mensagem_sucesso = f"❌ Patrimônio '{coluna_patrimonio_del}' e seu fabricante foram excluídos do setor '{setor_patrimonio_del}'."
                        st.session_state.gerenciador_exclusao_aberto = True
                        st.session_state.del_coluna_patrimonio = None
                        st.session_state.del_setor_patrimonio = setor_patrimonio_del
                    else:
                        st.session_state.mensagem_sucesso = f"⚠️ Nenhum patrimônio foi excluído para o setor '{setor_patrimonio_del}'."
                        st.session_state.gerenciador_exclusao_aberto = True
                    st.rerun()
'''
    pattern = re.compile(r'        with st\.expander\(f"🗑️ Gerenciador de Exclusão — Aba \(\{unidade\}\)".*?\n\n\nif __name__ == "__main__":', re.DOTALL)
    text, count = pattern.subn(lambda _: replacement + "\n\n\nif __name__ == \"__main__\":", text, count=1)
    if count != 1:
        raise SystemExit('Bloco do Gerenciador de Exclusao nao foi localizado.')
    path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    patch_backend()
    patch_ui()
    print('PATCH_OK')
