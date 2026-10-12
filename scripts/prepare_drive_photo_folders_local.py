#!/usr/bin/env python3
"""Prepare a local folder tree matching folders in the GTI SESA Google Drive.

Read-only access to Drive. Creates missing local directories only; it does not
download, move, rename, or delete files and never changes cloud content.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME = "application/vnd.google-apps.folder"
PAGE_SIZE = 1000


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value


def drive_service():
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if raw_json:
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(raw_json), scopes=SCOPES
        )
    elif key_file:
        credentials = service_account.Credentials.from_service_account_file(
            key_file, scopes=SCOPES
        )
    else:
        raise RuntimeError(
            "Configure GOOGLE_SERVICE_ACCOUNT_FILE ou "
            "GOOGLE_SERVICE_ACCOUNT_JSON no ambiente seguro."
        )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def safe_component(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).rstrip(". ")
    if value in {"", ".", ".."}:
        return "_sem_nome"
    return value[:180]


def list_children(service, parent_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    token = None
    while True:
        response = service.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            pageSize=PAGE_SIZE,
            pageToken=token,
            orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,shortcutDetails)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        items.extend(response.get("files", []))
        token = response.get("nextPageToken")
        if not token:
            return items


def unique_names(items: list[dict[str, Any]]) -> dict[str, str]:
    counts: dict[str, int] = {}
    for item in items:
        name = safe_component(item.get("name", ""))
        counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
    return {
        item["id"]: (
            safe_component(item.get("name", ""))
            if counts[safe_component(item.get("name", "")).casefold()] == 1
            else f"{safe_component(item.get('name', ''))}__{item['id'][:8]}"
        )
        for item in items
    }


def prepare_tree(service, folder_id: str, relative: Path, root: Path,
                 stats: dict[str, int], depth: int = 0) -> None:
    children = list_children(service, folder_id)
    folders = [
        item for item in children
        if item.get("mimeType") == FOLDER_MIME and not item.get("shortcutDetails")
    ]
    names = unique_names(folders)
    for folder in folders:
        next_relative = relative / names[folder["id"]]
        destination = (root / next_relative).resolve()
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("Caminho calculado saiu da raiz local permitida.") from exc
        existed = destination.is_dir()
        destination.mkdir(parents=True, exist_ok=True)
        if not destination.is_dir():
            raise RuntimeError(f"Não foi possível preparar a pasta: {destination}")
        if existed:
            stats["pastas_existentes"] += 1
            print(f"EXISTENTE | {next_relative}")
        else:
            stats["pastas_criadas"] += 1
            print(f"CRIADA | {next_relative}")
        if depth == 0:
            stats["pastas_raiz_unidade"] += 1
            print(f"UNIDADE/ABA (pasta de primeiro nível) | {next_relative}")
        prepare_tree(service, folder["id"], next_relative, root, stats, depth + 1)


def main() -> int:
    root_id = required_env("GOOGLE_DRIVE_ROOT_ID")
    root = Path(required_env("LOCAL_PHOTOS_ROOT")).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    service = drive_service()
    meta = service.files().get(
        fileId=root_id, fields="id,name,mimeType,trashed", supportsAllDrives=True
    ).execute()
    if meta.get("trashed"):
        raise RuntimeError("A pasta raiz configurada está na lixeira do Drive.")
    if meta.get("mimeType") != FOLDER_MIME:
        raise RuntimeError("GOOGLE_DRIVE_ROOT_ID não aponta para uma pasta do Drive.")

    stats = {"pastas_criadas": 0, "pastas_existentes": 0, "pastas_raiz_unidade": 0}
    print("GTI SESA | PREPARAÇÃO LOCAL DA ESTRUTURA DE PASTAS")
    print(f"Origem Drive: {meta.get('name')} (ID ocultado)")
    print(f"Destino local: {root}")
    print("Modo: cria apenas pastas ausentes; não baixa nem apaga arquivos.")
    prepare_tree(service, root_id, Path(), root, stats)
    print("RESUMO | " + " | ".join(f"{k}={v}" for k, v in stats.items()))
    print("Drive permaneceu somente leitura; nenhum arquivo da nuvem foi alterado.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[BLOQUEADO] {exc}", file=sys.stderr)
        raise SystemExit(2)
