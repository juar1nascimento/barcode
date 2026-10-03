"""Integração segura e idempotente de fotos do Supabase Storage -> Google Drive.

O Drive é o repositório documental das fotos. O Supabase permanece como
pulmão/orquestrador e fonte operacional. Nenhum arquivo é publicado como
"anyone with the link"; o acesso depende das permissões já existentes no
Drive/Shared Drive.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

import requests
import streamlit as st
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request

from supabase_storage import criar_url_assinada_storage

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
ROOT_FOLDER_ENV = "GOOGLE_DRIVE_ROOT_FOLDER_ID"
ROOT_FOLDER_SECRET = "root_folder_id"
FOLDER_PREFIX = "Fotos - Inventário GTI SESA"
TIMEOUT = 30


def _google_service_account() -> dict:
    sec = {}
    try:
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            sec = dict(st.secrets["connections"]["gsheets"])
        elif "gcp_service_account" in st.secrets:
            sec = dict(st.secrets["gcp_service_account"])
    except Exception:
        sec = {}

    if not sec:
        raw = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "").strip()
        if raw:
            sec = json.loads(raw)

    if not sec.get("client_email") or not sec.get("private_key"):
        raise RuntimeError("Credencial Google não configurada para o repositório de fotos.")

    return sec


def _root_folder_id() -> str:
    try:
        sec = dict(st.secrets.get("google_drive") or {})
    except Exception:
        sec = {}
    value = sec.get(ROOT_FOLDER_SECRET) or os.getenv(ROOT_FOLDER_ENV) or ""
    value = str(value).strip()
    if not value:
        raise RuntimeError("Configure google_drive.root_folder_id antes de habilitar a sincronização.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", value):
        raise RuntimeError("google_drive.root_folder_id inválido.")
    return value


def _token() -> str:
    credentials = Credentials.from_service_account_info(
        _google_service_account(),
        scopes=[DRIVE_SCOPE],
    )
    credentials.refresh(Request())
    if not credentials.token:
        raise RuntimeError("Google não retornou token de acesso ao Drive.")
    return credentials.token


def _headers(token: str, content_type: Optional[str] = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _drive_get(token: str, params: dict) -> dict:
    response = requests.get(
        f"{DRIVE_API}/files",
        headers=_headers(token),
        params=params,
        timeout=TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(f"Drive indisponível (HTTP {response.status_code}).")
    return response.json()


def _find_folder(token: str, parent_id: str, name: str) -> Optional[str]:
    escaped = name.replace("'", "\\'")
    data = _drive_get(
        token,
        {
            "q": (
                "mimeType='application/vnd.google-apps.folder' "
                "and trashed=false "
                f"and name='{escaped}' "
                f"and '{parent_id}' in parents"
            ),
            "pageSize": 10,
            "fields": "files(id,name,parents)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        },
    )
    files = data.get("files") or []
    return str(files[0]["id"]) if files else None


def _create_folder(token: str, parent_id: str, name: str) -> str:
    response = requests.post(
        f"{DRIVE_API}/files",
        headers=_headers(token, "application/json"),
        params={"supportsAllDrives": "true"},
        json={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        timeout=TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(f"Não foi possível criar a pasta do Drive (HTTP {response.status_code}).")
    folder_id = response.json().get("id")
    if not folder_id:
        raise RuntimeError("Drive não retornou o identificador da pasta.")
    return str(folder_id)


def _ensure_folder(token: str, parent_id: str, name: str) -> str:
    existing = _find_folder(token, parent_id, name)
    return existing or _create_folder(token, parent_id, name)


def pasta_patrimonio(token: str, unidade: str, numero: str) -> str:
    root = _root_folder_id()
    fotos_root = _ensure_folder(token, root, FOLDER_PREFIX)
    unidade_folder = _ensure_folder(token, fotos_root, _safe_name(unidade))
    return _ensure_folder(token, unidade_folder, f"Patrimônio {numero}")


def _safe_name(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|]+', "-", str(value or "").strip())
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:120] or "Sem identificação"


def _download_supabase_photo(bucket: str, path: str) -> bytes:
    url = criar_url_assinada_storage(bucket, path, expires_in=300)
    response = requests.get(url, timeout=TIMEOUT)
    if not response.ok:
        raise RuntimeError(f"Não foi possível ler a foto do Storage (HTTP {response.status_code}).")
    data = response.content
    if not data or len(data) > 1_048_576:
        raise RuntimeError("A foto recebida não atende ao limite operacional definido.")
    return data


def _find_existing_photo(token: str, folder_id: str, name: str, sha256: str) -> Optional[dict]:
    escaped = name.replace("'", "\\'")
    data = _drive_get(
        token,
        {
            "q": (
                "trashed=false "
                f"and name='{escaped}' "
                f"and '{folder_id}' in parents"
            ),
            "pageSize": 10,
            "fields": "files(id,name,md5Checksum,webViewLink,parents,size,appProperties)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        },
    )
    for item in data.get("files") or []:
        if item.get("md5Checksum"):
            # O SHA-256 é mantido no metadata do arquivo pelo app; md5 é só
            # um filtro adicional do Drive e nunca substitui a integridade do banco.
            if item.get("appProperties", {}).get("inventario_sha256") == sha256:
                return item
        elif item.get("name") == name:
            return item
    return None


def _upload_multipart(token: str, folder_id: str, name: str, data: bytes, sha256: str) -> dict:
    metadata = {
        "name": name,
        "parents": [folder_id],
        "mimeType": "image/jpeg",
        "description": "Inventário GTI SESA — foto patrimonial. Conteúdo sensível; acesso controlado.",
        "appProperties": {
            "sistema": "inventario-gti-sesa",
            "inventario_sha256": sha256,
        },
    }
    boundary = "inventario-gti-sesa-boundary"
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + json.dumps(metadata, ensure_ascii=False)
        + f"\r\n--{boundary}\r\n"
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    response = requests.post(
        f"{DRIVE_UPLOAD_API}/files",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        params={"uploadType": "multipart", "supportsAllDrives": "true"},
        data=body,
        timeout=TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(f"Falha no upload da foto ao Drive (HTTP {response.status_code}).")

    file_id = response.json().get("id")
    if not file_id:
        raise RuntimeError("Drive não retornou o identificador do arquivo.")
    return _get_file(token, str(file_id))


def _get_file(token: str, file_id: str) -> dict:
    response = requests.get(
        f"{DRIVE_API}/files/{file_id}",
        headers=_headers(token),
        params={
            "fields": "id,name,webViewLink,parents,size,mimeType,appProperties",
            "supportsAllDrives": "true",
        },
        timeout=TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(f"Não foi possível confirmar o arquivo no Drive (HTTP {response.status_code}).")
    return response.json()


def sincronizar_foto_drive(*, unidade: str, numero: str, ordem: int, bucket: str, path: str, sha256: str) -> dict:
    """Entrega uma foto no Drive de forma idempotente e sem compartilhamento público."""
    token = _token()
    folder_id = pasta_patrimonio(token, unidade, numero)
    name = f"{_safe_name(numero)} - Foto {int(ordem):02d}.jpg"

    existing = _find_existing_photo(token, folder_id, name, sha256)
    if existing:
        return {
            "id": str(existing["id"]),
            "name": str(existing.get("name") or name),
            "web_url": str(existing.get("webViewLink") or f"https://drive.google.com/file/d/{existing['id']}/view"),
            "folder_id": folder_id,
        }

    data = _download_supabase_photo(bucket, path)
    uploaded = _upload_multipart(token, folder_id, name, data, sha256)
    return {
        "id": str(uploaded["id"]),
        "name": str(uploaded.get("name") or name),
        "web_url": str(uploaded.get("webViewLink") or f"https://drive.google.com/file/d/{uploaded['id']}/view"),
        "folder_id": folder_id,
    }
