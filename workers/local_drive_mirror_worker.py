#!/usr/bin/env python3
"""
GTI SESA - Local mirror worker for Google Drive.

Safety:
- dry-run is the default;
- no Drive deletion in dry-run;
- processing starts only at >= 1 GiB pending;
- FIFO is ordem_fila ASC, id ASC;
- local path is derived from the exact Drive parent chain up to GOOGLE_DRIVE_ROOT_ID;
- live mode downloads directly from Drive API when the local file is absent or invalid;
- download uses a temporary file and verifies size + SHA-256 before replacing the destination;
- Drive deletion additionally requires --live and LOCAL_MIRROR_ALLOW_DELETE=true;
- failures keep the Drive source intact.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build, MediaIoBaseDownload
from googleapiclient.errors import HttpError


TABLE = "patrimonio_fotos_local_outbox"
DEFAULT_THRESHOLD = 1024 ** 3
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value


SUPABASE_URL = env_required("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = env_required("SUPABASE_SERVICE_ROLE_KEY")
LOCAL_ROOT = Path(env_required("LOCAL_MIRROR_ROOT")).resolve()
DRIVE_ROOT_ID = env_required("GOOGLE_DRIVE_ROOT_ID")
THRESHOLD = int(os.getenv("LOCAL_MIRROR_THRESHOLD_BYTES", str(DEFAULT_THRESHOLD)))
BATCH_BYTES = int(os.getenv("LOCAL_MIRROR_BATCH_BYTES", str(DEFAULT_THRESHOLD)))
MAX_ATTEMPTS = int(os.getenv("LOCAL_MIRROR_MAX_ATTEMPTS", "12"))
ALLOW_DELETE = os.getenv("LOCAL_MIRROR_ALLOW_DELETE", "false").lower() == "true"
DRY_RUN_ENV = os.getenv("LOCAL_MIRROR_DRY_RUN", "true").lower() == "true"


def sb_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def sb_get(params: dict[str, str]) -> list[dict[str, Any]]:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{TABLE}",
        headers=sb_headers(),
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sb_patch(row_id: int, values: dict[str, Any], expected_status: str | None = None) -> list[dict[str, Any]]:
    params = {"id": f"eq.{row_id}"}
    if expected_status:
        params["status"] = f"eq.{expected_status}"
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{TABLE}",
        headers={**sb_headers(), "Prefer": "return=representation"},
        params=params,
        json=values,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def drive_service():
    raw = env_required("GOOGLE_SERVICE_ACCOUNT_JSON")
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=DRIVE_SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def drive_metadata(service, file_id: str) -> dict[str, Any]:
    return service.files().get(
        fileId=file_id,
        fields="id,name,size,trashed,parents,webViewLink",
        supportsAllDrives=True,
    ).execute()


def drive_parent_metadata(service, folder_id: str) -> dict[str, Any]:
    return service.files().get(
        fileId=folder_id,
        fields="id,name,mimeType,parents,trashed",
        supportsAllDrives=True,
    ).execute()


def exact_local_path(service, file_meta: dict[str, Any]) -> Path:
    names: list[str] = [file_meta["name"]]
    parents = file_meta.get("parents") or []
    if len(parents) != 1:
        raise RuntimeError(
            f"Mapeamento Drive ambíguo: arquivo {file_meta['id']} possui "
            f"{len(parents)} pais diretos; esperado exatamente 1."
        )

    current_id = parents[0]
    visited: set[str] = set()

    while current_id != DRIVE_ROOT_ID:
        if current_id in visited:
            raise RuntimeError("Ciclo detectado na hierarquia do Drive.")
        visited.add(current_id)

        meta = drive_parent_metadata(service, current_id)
        if meta.get("trashed"):
            raise RuntimeError(f"Pasta Drive na lixeira: {current_id}")
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            raise RuntimeError(f"Pai do arquivo não é pasta: {current_id}")

        names.append(meta["name"])
        parent_ids = meta.get("parents") or []
        if len(parent_ids) != 1:
            raise RuntimeError(
                f"Pasta {current_id} não possui exatamente um pai; "
                "não é seguro reconstruir o caminho local."
            )
        current_id = parent_ids[0]

    names.reverse()
    candidate = (LOCAL_ROOT.joinpath(*names)).resolve()

    try:
        candidate.relative_to(LOCAL_ROOT)
    except ValueError as exc:
        raise RuntimeError("Caminho local saiu da raiz configurada.") from exc

    return candidate


def download_drive_file(service, file_id: str, destination: Path, expected_size: int, expected_sha256: str) -> str:
    """Download to a temporary file, verify it, then atomically replace destination."""
    destination = destination.resolve()
    destination.relative_to(LOCAL_ROOT)

    if destination.is_symlink():
        raise RuntimeError(f"Destino local é link simbólico; download bloqueado: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".gti-{file_id}-",
        suffix=".part",
        dir=str(destination.parent),
    )
    os.close(fd)
    temp_path = Path(temp_name)

    try:
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        downloader = MediaIoBaseDownload(
            open(temp_path, "wb"),
            request,
            chunksize=8 * 1024 * 1024,
        )
        done = False
        with temp_path.open("wb") as fh:
            downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
            while not done:
                _, done = downloader.next_chunk()

        actual_size = temp_path.stat().st_size
        if actual_size != expected_size:
            raise RuntimeError(
                f"Tamanho baixado divergente: esperado={expected_size}, local={actual_size}"
            )

        digest = sha256_file(temp_path)
        if digest.lower() != expected_sha256.lower():
            raise RuntimeError(
                f"SHA-256 do download divergente: esperado={expected_sha256}, local={digest}"
            )

        os.replace(temp_path, destination)
        return digest
    finally:
        if temp_path.exists():
            temp_path.unlink()


def claim(row: dict[str, Any]) -> dict[str, Any] | None:
    if DRY_RUN_ENV:
        return row
    updated = sb_patch(
        int(row["id"]),
        {
            "status": "processing",
            "processando_em": utc_now(),
            "tentativas": int(row.get("tentativas") or 0) + 1,
        },
        expected_status="pending",
    )
    return updated[0] if updated else None


def fail(row: dict[str, Any], message: str) -> None:
    if DRY_RUN_ENV:
        return
    attempts = int(row.get("tentativas") or 0)
    status = "dead_letter" if attempts >= MAX_ATTEMPTS else "failed"
    sb_patch(
        int(row["id"]),
        {"status": status, "ultimo_erro": message[:4000]},
        expected_status="processing",
    )


def mark_drive_delete_pending(row: dict[str, Any], local_path: Path, digest: str) -> None:
    if DRY_RUN_ENV:
        return
    sb_patch(
        int(row["id"]),
        {
            "status": "drive_delete_pending",
            "caminho_local": str(local_path),
            "sha256_local": digest,
            "baixado_em": utc_now(),
            "verificado_em": utc_now(),
            "ultimo_erro": None,
        },
        expected_status="processing",
    )


def complete_after_drive_delete(row: dict[str, Any]) -> None:
    if DRY_RUN_ENV:
        return
    sb_patch(
        int(row["id"]),
        {
            "status": "completed",
            "removido_drive_em": utc_now(),
            "ultimo_erro": None,
        },
        expected_status="drive_delete_pending",
    )


def status_rows(status: str) -> list[dict[str, Any]]:
    return sb_get(
        {
            "select": "*",
            "status": f"eq.{status}",
            "order": "ordem_fila.asc,id.asc",
            "limit": "500",
        }
    )


def pending_rows() -> list[dict[str, Any]]:
    return status_rows("pending")


def recover_drive_delete_pending(service) -> None:
    for row in status_rows("drive_delete_pending"):
        file_id = row["drive_file_id"]
        try:
            meta = drive_metadata(service, file_id)
            if meta.get("trashed"):
                complete_after_drive_delete(row)
                print(f"RECUPERADO | Drive já estava na lixeira | id={row['id']}")
                continue

            local_path = Path(row["caminho_local"])
            if not local_path.is_file():
                raise FileNotFoundError(f"Arquivo local ausente: {local_path}")

            expected_size = int(row["tamanho_bytes"])
            if local_path.stat().st_size != expected_size:
                raise RuntimeError("Tamanho local divergente na recuperação.")

            digest = sha256_file(local_path)
            if digest.lower() != row["drive_sha256"].lower():
                raise RuntimeError("SHA-256 divergente na recuperação.")

            service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            complete_after_drive_delete(row)
            print(f"RECUPERADO | Drive removido e estado concluído | id={row['id']}")
        except HttpError as exc:
            if getattr(exc, "resp", None) is not None and exc.resp.status == 404:
                complete_after_drive_delete(row)
                print(f"RECUPERADO | arquivo Drive já não existe | id={row['id']}")
            else:
                print(f"RECUPERAÇÃO FALHOU | id={row['id']} | {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"RECUPERAÇÃO FALHOU | id={row['id']} | {exc}", file=sys.stderr)


def run(dry_run: bool) -> int:
    global DRY_RUN_ENV
    DRY_RUN_ENV = dry_run

    rows = pending_rows()
    recovery = status_rows("drive_delete_pending")
    if recovery:
        service = drive_service()
        if not dry_run and not ALLOW_DELETE:
            print("RECUPERAÇÃO BLOQUEADA: LOCAL_MIRROR_ALLOW_DELETE != true", file=sys.stderr)
        elif not dry_run:
            recover_drive_delete_pending(service)
        else:
            print(f"DRY-RUN: {len(recovery)} registro(s) em drive_delete_pending não serão alterados.")

    total = sum(int(row["tamanho_bytes"]) for row in rows)
    print(f"Pendentes: {len(rows)} | volume: {total} bytes")

    if total < THRESHOLD:
        print(f"Gate 1 GB: NÃO atingido ({total}/{THRESHOLD} bytes). Nenhum processamento.")
        return 0

    if not dry_run and not ALLOW_DELETE:
        raise RuntimeError("Exclusão bloqueada: LOCAL_MIRROR_ALLOW_DELETE != true")

    service = drive_service()
    consumed = 0

    for original in rows:
        size = int(original["tamanho_bytes"])
        if consumed and consumed + size > BATCH_BYTES:
            break

        row = claim(original)
        if row is None:
            print(f"ID {original['id']}: claim perdido; seguindo.")
            continue

        file_id = row["drive_file_id"]
        try:
            meta = drive_metadata(service, file_id)
            if meta.get("trashed"):
                raise RuntimeError("Arquivo Drive já está na lixeira.")

            expected_size = int(row["tamanho_bytes"])
            actual_drive_size = int(meta.get("size") or 0)
            if actual_drive_size != expected_size:
                raise RuntimeError(
                    f"Tamanho Drive divergente: esperado={expected_size}, Drive={actual_drive_size}"
                )

            local_path = exact_local_path(service, meta)
            existing_ok = False
            if local_path.exists():
                if local_path.is_symlink():
                    raise RuntimeError(f"Destino local é link simbólico: {local_path}")
                if not local_path.is_file():
                    raise RuntimeError(f"Destino local não é arquivo: {local_path}")
                local_size = local_path.stat().st_size
                if local_size == expected_size:
                    digest = sha256_file(local_path)
                    existing_ok = digest.lower() == row["drive_sha256"].lower()
                    if existing_ok:
                        print(
                            f"OK LOCAL EXISTENTE | id={row['id']} | foto={row['foto_id']} | "
                            f"{local_path} | sha256={digest}"
                        )

            if not existing_ok:
                if dry_run:
                    print(
                        f"DRY-RUN | id={row['id']} | foto={row['foto_id']} | "
                        f"seria baixado para {local_path}"
                    )
                    consumed += size
                    continue

                digest = download_drive_file(
                    service,
                    file_id,
                    local_path,
                    expected_size,
                    row["drive_sha256"],
                )
                print(
                    f"DOWNLOAD + VERIFICAÇÃO OK | id={row['id']} | foto={row['foto_id']} | "
                    f"{local_path} | sha256={digest}"
                )

            if dry_run:
                print("DRY-RUN: nenhuma exclusão nem mutação do outbox.")
            else:
                mark_drive_delete_pending(row, local_path, digest)
                service.files().delete(
                    fileId=file_id,
                    supportsAllDrives=True,
                ).execute()
                complete_after_drive_delete(row)
                print(f"DRIVE REMOVIDO APÓS VERIFICAÇÃO | {file_id}")

            consumed += size

        except Exception as exc:
            print(f"FALHA | id={row['id']} | {exc}", file=sys.stderr)
            fail(row, str(exc))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if args.dry_run and args.live:
        parser.error("Use --dry-run ou --live, não ambos.")

    return run(not args.live)


if __name__ == "__main__":
    raise SystemExit(main())
