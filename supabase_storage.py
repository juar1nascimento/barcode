"""Cliente mínimo do Supabase Storage para o Sistema de Inventários GTI-SESA.

O módulo usa a API HTTP do Storage no lado servidor (Streamlit). A chave
service_role deve permanecer somente nas Secrets do servidor e nunca ser
exposta ao navegador.
"""

from __future__ import annotations

from typing import Optional

import requests
import streamlit as st


def _config() -> tuple[str, str]:
    sec = st.secrets.get("supabase", {})
    url = str(sec.get("url", "")).strip().rstrip("/")
    key = str(sec.get("service_role_key", "")).strip()
    if not url or not key:
        raise RuntimeError(
            "Secrets [supabase] incompletas: configure url e service_role_key."
        )
    return url, key


def _headers(key: str, content_type: Optional[str] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def upload_bytes(
    bucket: str,
    path: str,
    data: bytes,
    mime_type: str = "image/jpeg",
    timeout: int = 30,
) -> None:
    if not data:
        raise ValueError("Não é possível enviar um arquivo vazio.")
    url, key = _config()
    endpoint = f"{url}/storage/v1/object/{bucket}/{path.lstrip('/')}"
    response = requests.post(
        endpoint,
        headers=_headers(key, mime_type),
        data=data,
        timeout=timeout,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Falha no upload do Storage ({response.status_code}): "
            f"{response.text[:500]}"
        )


def download_bytes(
    bucket: str,
    path: str,
    timeout: int = 30,
) -> bytes:
    url, key = _config()
    endpoint = f"{url}/storage/v1/object/{bucket}/{path.lstrip('/')}"
    response = requests.get(
        endpoint,
        headers=_headers(key),
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Falha ao baixar objeto do Storage ({response.status_code}): "
            f"{response.text[:500]}"
        )
    return response.content


def create_signed_url(
    bucket: str,
    path: str,
    expires_in: int = 3600,
    timeout: int = 30,
) -> str:
    if expires_in <= 0:
        raise ValueError("expires_in deve ser maior que zero.")
    url, key = _config()
    endpoint = f"{url}/storage/v1/object/sign/{bucket}/{path.lstrip('/')}"
    response = requests.post(
        endpoint,
        headers=_headers(key, "application/json"),
        json={"expiresIn": expires_in},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Falha ao criar URL assinada ({response.status_code}): "
            f"{response.text[:500]}"
        )
    payload = response.json()
    signed = payload.get("signedURL") or payload.get("signedUrl")
    if not signed:
        raise RuntimeError("O Storage não retornou signedURL.")
    if signed.startswith("http"):
        return signed
    return f"{url}/storage/v1{signed}"
