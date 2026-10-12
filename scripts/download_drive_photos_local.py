#!/usr/bin/env python3
"""Baixa SOMENTE arquivos de imagem de uma pasta do Google Drive para o PC local.

Modo padrão: simulação (não grava arquivos).
Modo --download: baixa imagens e preserva a hierarquia de pastas do Drive.
Nunca exclui, move, renomeia ou altera arquivos na nuvem nem apaga arquivos locais.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
IMAGE_PREFIX = "image/"
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
        info = json.loads(raw_json)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    elif key_file:
        credentials = service_account.Credentials.from_service_account_file(
            key_file, scopes=SCOPES
        )
    else:
        raise RuntimeError(
            "Configure GOOGLE_SERVICE_ACCOUNT_FILE (caminho local do JSON) "
            "ou GOOGLE_SERVICE_ACCOUNT_JSON no ambiente seguro."
        )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def safe_component(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = value.rstrip(". ")
    if value in {"", ".", ".."}:
        return "_sem_nome"
    return value[:180]


def list_children(service, parent_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    token = None
    while True:
        response = service.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            pageSize=PAGE_SIZE,
            pageToken=token,
            orderBy="name",
            fields=(
                "nextPageToken,files(id,name,mimeType,size,md5Checksum,parents,"
                "webViewLink,shortcutDetails)"
            ),
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        result.extend(response.get("files", []))
        token = response.get("nextPageToken")
        if not token:
            return result


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


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_image(service, file_meta: dict[str, Any], destination: Path) -> None:
    expected_size = int(file_meta.get("size") or 0)
    expected_md5 = str(file_meta.get("md5Checksum") or "").lower()
    destination.parent.mkdir(parents=True, exist_ok=True)
    root = Path(required_env("LOCAL_PHOTOS_ROOT")).expanduser().resolve()
    resolved = destination.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("Destino calculado saiu da pasta local permitida.") from exc

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            request = service.files().get_media(
                fileId=file_meta["id"], supportsAllDrives=True
            )
            downloader = MediaIoBaseDownload(handle, request, chunksize=1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            handle.flush()
            os.fsync(handle.fileno())

        actual_size = temp_path.stat().st_size
        if expected_size and actual_size != expected_size:
            raise RuntimeError(
                f"Tamanho divergente para {file_meta.get('name')}: "
                f"esperado={expected_size}, recebido={actual_size}"
            )
        actual_md5 = md5_file(temp_path)
        if expected_md5 and actual_md5 != expected_md5:
            raise RuntimeError(f"MD5 divergente para {file_meta.get('name')}")
        os.replace(temp_path, destination)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def walk_drive(service, folder_id: str, relative: Path, root: Path,
               download: bool, stats: dict[str, int]) -> None:
    children = list_children(service, folder_id)
    folders = [
        item for item in children
        if item.get("mimeType") == "application/vnd.google-apps.folder"
    ]
    name_map = unique_names(folders)

    for folder in folders:
        walk_drive(
            service,
            folder["id"],
            relative / name_map[folder["id"]],
            root,
            download,
            stats,
        )

    images = [
        item for item in children
        if str(item.get("mimeType", "")).startswith(IMAGE_PREFIX)
        and not item.get("shortcutDetails")
    ]
    image_names = unique_names(images)
    for item in images:
        name = image_names[item["id"]]
        destination = (root / relative / name).resolve()
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("Caminho de imagem fora da raiz local.") from exc

        stats["images_found"] += 1
        size = int(item.get("size") or 0)
        if destination.is_file():
            same_size = not size or destination.stat().st_size == size
            same_md5 = (
                not item.get("md5Checksum")
                or md5_file(destination) == str(item["md5Checksum"]).lower()
            )
            if same_size and same_md5:
                stats["already_current"] += 1
                print(f"OK LOCAL | {relative / name}")
                continue
            # Non-destructive mirror: never replace a pre-existing local file whose
            # contents differ from the Drive object. Preserve it and report conflict.
            stats["conflicts_preserved"] += 1
            print(
                f"CONFLITO LOCAL (preservado; sem sobrescrita) | {relative / name} "
                f"| drive_id={item.get("id")}"
            )
            continue

        if not download:
            stats["would_download"] += 1
            print(f"SIMULAÇÃO | baixaria {relative / name} ({size} bytes)")
            continue

        download_image(service, item, destination)
        stats["downloaded"] += 1
        print(f"BAIXADA E VERIFICADA | {relative / name} ({size} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Baixa somente imagens do Google Drive; nunca exclui arquivos."
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Executa os downloads. Sem esta opção, apenas simula.",
    )
    args = parser.parse_args()

    root_id = required_env("GOOGLE_DRIVE_ROOT_ID")
    root = Path(required_env("LOCAL_PHOTOS_ROOT")).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    service = drive_service()
    root_meta = service.files().get(
        fileId=root_id,
        fields="id,name,mimeType,trashed",
        supportsAllDrives=True,
    ).execute()
    if root_meta.get("trashed"):
        raise RuntimeError("A pasta raiz configurada está na lixeira.")
    if root_meta.get("mimeType") != "application/vnd.google-apps.folder":
        raise RuntimeError("GOOGLE_DRIVE_ROOT_ID não aponta para uma pasta do Drive.")

    stats = {"images_found": 0, "already_current": 0, "would_download": 0, "downloaded": 0, "conflicts_preserved": 0}
    print(f"Origem Drive: {root_meta.get('name')} (ID ocultado)")
    print(f"Destino local: {root}")
    print("Filtro: somente MIME type image/*; nenhum outro tipo será baixado.")
    print(f"Modo: {'DOWNLOAD' if args.download else 'SIMULAÇÃO'}")
    walk_drive(service, root_id, Path(), root, args.download, stats)
    print("RESUMO | " + " | ".join(f"{k}={v}" for k, v in stats.items()))
    print("NENHUM arquivo na nuvem foi alterado ou excluído.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[BLOQUEADO] {exc}", file=sys.stderr)
        raise SystemExit(2)
