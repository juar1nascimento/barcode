"""Preflight não destrutivo da configuração Supabase.

Não exibe nem registra valores de credenciais.
"""
from __future__ import annotations

import streamlit as st


def verificar_secrets_supabase() -> dict[str, bool]:
    """Retorna somente indicadores booleanos, sem expor Secrets."""
    sec = st.secrets.get("supabase")
    if not sec:
        return {
            "bloco_supabase": False,
            "url": False,
            "chave": False,
            "configuracao_pronta": False,
        }

    url = str(sec.get("url") or "").strip().rstrip("/")
    key = str(sec.get("secret_key") or sec.get("service_role_key") or "").strip()

    return {
        "bloco_supabase": True,
        "url": bool(url),
        "chave": bool(key),
        "configuracao_pronta": bool(url and key),
    }
