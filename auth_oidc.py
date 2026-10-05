"""Adaptador OIDC isolado para homologação do Keycloak.

Este módulo não é ativado pela aplicação atual. O login local continua sendo
a autoridade em produção até que exista um provedor OIDC real e validado.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def oidc_configurado() -> bool:
    """Retorna True somente quando a configuração [auth] mínima existe."""
    try:
        cfg = st.secrets.get("auth", {})
    except Exception:
        return False

    required = ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url")
    return all(str(cfg.get(item, "")).strip() for item in required)


def usuario_oidc() -> dict[str, Any] | None:
    """Extrai apenas claims não sensíveis da sessão OIDC."""
    if not oidc_configurado():
        return None

    try:
        user = st.user
    except Exception:
        return None

    if not getattr(user, "is_logged_in", False):
        return None

    email = str(getattr(user, "email", "") or "").strip().lower()
    username = str(getattr(user, "preferred_username", "") or "").strip().lower()
    name = str(getattr(user, "name", "") or "").strip()

    if not email and not username:
        return None

    return {
        "email": email,
        "preferred_username": username,
        "name": name,
    }


def iniciar_login_oidc() -> None:
    """Inicia o fluxo OIDC gerenciado pelo Streamlit."""
    if not oidc_configurado():
        raise RuntimeError("OIDC não configurado no ambiente de homologação.")
    st.login()


def encerrar_login_oidc() -> None:
    """Encerra a sessão OIDC gerenciada pelo Streamlit."""
    st.logout()
