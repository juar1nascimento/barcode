"""Ponte de persistência dupla para o módulo de inventário.

Quando a Secret [postgresql] estiver configurada, cada novo cadastro passa
primeiro pelo PostgreSQL e depois pelo Google Sheets. Sem PostgreSQL configurado,
o comportamento existente do Google Sheets permanece inalterado.
"""

import streamlit as st

import postgresql_persistencia
from persistencia_fotos_patrimonio import FotoPatrimonioPersistenciaError, salvar_foto_patrimonio

_original = None


def ativar():
    """Ativa o espelhamento PostgreSQL + Google Sheets durante a página."""
    global _original
    if _original is not None:
        return

    import sistema_inventario
    _original = sistema_inventario.adicionar_e_salvar

    def wrapper(codigo, patrimonio, setor, unidade, fabricante=""):
        st.session_state["ultimo_patrimonio_id"] = None

        if not postgresql_persistencia._conexao_configurada():
            return _original(codigo, patrimonio, setor, unidade, fabricante)

        ok_pg, patrimonio_id, msg_pg = postgresql_persistencia.salvar_patrimonio(
            codigo_barras=codigo,
            tipo=patrimonio,
            setor=setor,
            unidade=unidade,
            fabricante=fabricante,
        )
        if not ok_pg:
            st.error(f"❌ Cadastro não concluído: {msg_pg}")
            return False

        st.session_state["ultimo_patrimonio_id"] = patrimonio_id

        foto = st.session_state.get("foto_patrimonio_processada")
        if foto is not None and patrimonio_id is not None:
            try:
                resultado_foto = salvar_foto_patrimonio(int(patrimonio_id), foto)
            except (FotoPatrimonioPersistenciaError, PermissionError) as exc:
                st.error(f"❌ O patrimônio foi gravado, mas a foto não foi armazenada: {exc}")
                return False
            except Exception as exc:
                st.error(f"❌ O patrimônio foi gravado, mas a foto não foi armazenada: {exc}")
                return False
            else:
                st.session_state["foto_patrimonio_ultima_ordem"] = resultado_foto.ordem
                st.session_state.pop("foto_patrimonio_processada", None)
                st.session_state.pop("foto_patrimonio_sha256", None)
                st.success(
                    f"📷 Foto {resultado_foto.ordem} armazenada automaticamente no patrimônio."
                )

        ok_sheets = _original(codigo, patrimonio, setor, unidade, fabricante)
        if not ok_sheets:
            st.warning(
                "⚠️ O patrimônio foi gravado no PostgreSQL, mas o Google Sheets "
                "não confirmou o espelhamento. O registro não foi descartado. "
                "Será necessário sincronizar o Sheets posteriormente."
            )
            return False
        return True

    sistema_inventario.adicionar_e_salvar = wrapper


def desativar():
    global _original
    if _original is None:
        return
    import sistema_inventario
    sistema_inventario.adicionar_e_salvar = _original
    _original = None
