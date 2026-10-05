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

    required = (
        "redirect_uri",
        "cookie_secret",
        "client_id",
        "client_secret",
        "server_metadata_url",
    )
    return all(str(cfg.get(item, "")).strip() for item in required)


def _claim(nome: str, padrao: Any = None) -> Any:
    """Lê claim sem assumir que st.user é dict ou objeto."""
    try:
        user = st.user
        if isinstance(user, dict):
            return user.get(nome, padrao)
        return getattr(user, nome, padrao)
    except Exception:
        return padrao


def _normalizar_roles(valor: Any) -> set[str]:
    """Normaliza roles vindas de diferentes mapeamentos OIDC."""
    if isinstance(valor, str):
        valores = [valor]
    elif isinstance(valor, (list, tuple, set)):
        valores = valor
    else:
        valores = []

    return {
        str(item).strip().lower()
        for item in valores
        if str(item).strip()
    }


def usuario_oidc() -> dict[str, Any] | None:
    """Extrai somente identidade mínima e roles explícitas da sessão OIDC."""
    if not oidc_configurado():
        return None

    if not bool(_claim("is_logged_in", False)):
        return None

    # O sub é o identificador técnico estável do IdP e é obrigatório.
    subject = str(_claim("sub", "") or "").strip()
    if not subject:
        return None

    email = str(_claim("email", "") or "").strip().lower()
    username = str(_claim("preferred_username", "") or "").strip().lower()
    name = str(_claim("name", "") or "").strip()

    if not email and not username:
        return None

    roles = _normalizar_roles(_claim("roles", []))

    # Compatibilidade com um mapper Keycloak que entregue realm_access.roles.
    realm_access = _claim("realm_access", {})
    if isinstance(realm_access, dict):
        roles.update(_normalizar_roles(realm_access.get("roles", [])))

    return {
        "sub": subject,
        "email": email,
        "preferred_username": username,
        "name": name,
        "roles": roles,
        "is_admin": "admin" in roles,
    }


def iniciar_login_oidc() -> None:
    """Inicia o fluxo OIDC gerenciado pelo Streamlit."""
    if not oidc_configurado():
        raise RuntimeError("OIDC não configurado no ambiente de homologação.")
    st.login()


def encerrar_login_oidc() -> None:
    """Encerra a sessão OIDC gerenciada pelo Streamlit."""
    st.logout()
