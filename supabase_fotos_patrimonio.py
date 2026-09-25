"""Infraestrutura server-side para persistência segura de fotos no Supabase.

Este módulo não deve ser importado por código executado no navegador.
A chave privilegiada, quando usada, deve permanecer exclusivamente em
st.secrets no servidor Streamlit.
"""

from __future__ import annotations

from typing import Any

import streamlit as st
from supabase import Client, create_client


class SupabaseFotosConfigError(RuntimeError):
    """Configuração necessária para persistência de fotos ausente ou inválida."""


def usuario_app_autorizado() -> bool:
    """Confirma a sessão do login próprio antes de qualquer operação de foto.

    O projeto não usa Supabase Auth atualmente. Portanto, esta verificação
    é deliberadamente baseada no mecanismo de autenticação existente no app.
    Ela será chamada no servidor, antes do acesso privilegiado ao Supabase.
    """

    autenticado = st.session_state.get("autenticado") is True
    usuario = st.session_state.get("usuario_logado")
    return autenticado and bool(usuario)


def _ler_segredo(nome: str) -> str:
    """Lê uma configuração obrigatória sem expor seu valor em logs/UI."""

    try:
        valor: Any = st.secrets[nome]
    except (KeyError, FileNotFoundError):
        valor = None

    if valor is None or not str(valor).strip():
        raise SupabaseFotosConfigError(
            f"Configuração server-side ausente: {nome}"
        )

    return str(valor).strip()


def criar_cliente_supabase_servidor() -> Client:
    """Cria um cliente Supabase exclusivamente no servidor.

    Chaves aceitas:
    - [supabase].url + [supabase].service_role_key
    - [supabase].url + [supabase].secret_key

    A chave nunca deve ser colocada em código, enviada ao navegador ou
    armazenada em session_state.
    """

    url = _ler_segredo("supabase.url")

    try:
        chave = _ler_segredo("supabase.service_role_key")
    except SupabaseFotosConfigError:
        chave = _ler_segredo("supabase.secret_key")

    return create_client(url, chave)


def validar_acesso_fotos() -> Client:
    """Valida a sessão do aplicativo e retorna o cliente privilegiado.

    Não realiza upload nem alteração no banco. É apenas a barreira de entrada
    para a futura operação transacional de Storage + patrimonio_fotos.
    """

    if not usuario_app_autorizado():
        raise PermissionError("Sessão do aplicativo não autorizada para fotos.")

    return criar_cliente_supabase_servidor()
