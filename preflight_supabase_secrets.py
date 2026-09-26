"""Preflight não destrutivo da configuração Supabase.

Não exibe nem registra valores de credenciais.
"""
from __future__ import annotations

import requests
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


def testar_acesso_storage() -> tuple[bool, str]:
    """Testa somente leitura do bucket, sem criar/alterar objetos."""
    status = verificar_secrets_supabase()
    if not status["configuracao_pronta"]:
        return False, "Secrets do Supabase não estão completas."

    sec = st.secrets["supabase"]
    url = str(sec.get("url") or "").strip().rstrip("/")
    key = str(sec.get("secret_key") or sec.get("service_role_key") or "").strip()

    try:
        response = requests.get(
            f"{url}/storage/v1/bucket/patrimonio-fotos",
            headers={
                "Authorization": f"Bearer {key}",
                "apikey": key,
            },
            timeout=15,
        )
    except requests.RequestException:
        return False, "Não foi possível alcançar o Storage do Supabase."

    if response.ok:
        return True, "Acesso de leitura ao bucket patrimônio-fotos confirmado."

    if response.status_code in (401, 403):
        return False, "Storage respondeu, mas a credencial não foi aceita."

    if response.status_code == 404:
        return False, "Bucket patrimônio-fotos não encontrado."

    return False, f"Storage respondeu HTTP {response.status_code}."
