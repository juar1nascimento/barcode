import os
import re
from typing import Any
import streamlit as st
from supabase import Client, create_client

EMAIL_RE = re.compile(r"^[\w.\-+]+@[\w.\-]+\.\w+$")

def _config() -> tuple[str, str]:
    cfg = st.secrets.get("supabase", {})
    url = str(cfg.get("url") or os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = str(cfg.get("publishable_key") or cfg.get("anon_key") or os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("Configuração pública do Supabase ausente.")
    return url, key

def client() -> Client:
    c = st.session_state.get("_supabase_auth_client")
    if c is None:
        url, key = _config()
        c = create_client(url, key)
        st.session_state["_supabase_auth_client"] = c
    return c

def validar_email(email: str) -> bool:
    return bool(EMAIL_RE.fullmatch(str(email or "").strip()))

def senha_forte(senha: str) -> tuple[bool, str]:
    if len(senha) < 12:
        return False, "A senha deve ter pelo menos 12 caracteres."
    if not any(c.islower() for c in senha):
        return False, "A senha deve conter letra minúscula."
    if not any(c.isupper() for c in senha):
        return False, "A senha deve conter letra maiúscula."
    if not any(c.isdigit() for c in senha):
        return False, "A senha deve conter número."
    if not any(not c.isalnum() for c in senha):
        return False, "A senha deve conter símbolo."
    return True, ""

def sign_in(email: str, password: str):
    return client().auth.sign_in_with_password({"email": email.strip().lower(), "password": password})

def sign_up(email: str, password: str, nome: str = ""):
    return client().auth.sign_up({"email": email.strip().lower(), "password": password, "options": {"data": {"nome": nome.strip()}}})

def request_password_reset(email: str, redirect_to: str):
    return client().auth.reset_password_for_email(email.strip().lower(), {"redirect_to": redirect_to})

def exchange_code(code: str):
    return client().auth.exchange_code_for_session({"auth_code": code})

def update_password(password: str):
    return client().auth.update_user({"password": password})

def get_user():
    return client().auth.get_user()

def get_profile(user_id: str) -> dict[str, Any] | None:
    response = client().table("perfis_usuarios").select("id,email,nome,papel,aprovado,ativo").eq("id", user_id).maybe_single().execute()
    return response.data if response and response.data else None

def sign_out():
    try:
        client().auth.sign_out({"scope": "local"})
    except Exception:
        pass
