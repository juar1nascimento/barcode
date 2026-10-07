#!/usr/bin/env python3
"""
GTI SESA - Local Drive for Desktop mirror worker.

Safety model:
- DRY RUN is the default; it never deletes Drive files or mutates outbox state.
- Real mode requires LOCAL_MIRROR_ALLOW_DELETE=true.
- Processing starts only when pending bytes reach LOCAL_MIRROR_THRESHOLD_BYTES
  (default: 1 GiB).
- FIFO is ordem_fila ASC, id ASC.
- A local file is accepted only when exactly one matching path is found.
- Verification requires local size == expected size and SHA-256 == expected hash.
- Only after successful verification is the Drive object deleted.
- Any failure leaves the Drive source intact and records the error for retry.

Required environment:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  LOCAL_MIRROR_ROOT
  GOOGLE_SERVICE_ACCOUNT_JSON

Optional:
  LOCAL_MIRROR_THRESHOLD_BYTES=1073741824
  LOCAL_MIRROR_BATCH_BYTES=1073741824
  LOCAL_MIRROR_MAX_ATTEMPTS=12
  LOCAL_MIRROR_ALLOW_DELETE=false
  LOCAL_MIRROR_DRY_RUN=true
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build


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
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def find_unique_local_file(name: str) -> Path:
    matches = []
    for p in LOCAL_ROOT.rglob(name):
        if p.is_file():
            matches.append(p)
            if len(matches) > 1:
                break
    if not matches:
        raise FileNotFoundError(f"Arquivo não encontrado no espelho local: {name}")
    if len(matches) > 1:
        raise RuntimeError(
            f"Mapeamento ambíguo: {len(matches)} arquivos locais possuem o nome {name!r}"
        )
    return matches[0]


def claim(row: dict[str, Any]) -> dict[str, Any] | None:
    if DRY_RUN_ENV:
        return row
    updated = sb_patch(
        int(row["id"]),
        {
            "status": "processing",
            "processando_em": "now()",
            "tentativas": int(row.get("tentativas") or 0) + 1,
            "atualizado_em": "now()",
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
        {
            "status": status,
            "ultimo_erro": message[:4000],
            "atualizado_em": "now()",
        },
        expected_status="processing",
    )


def complete(row: dict[str, Any], local_path: Path, digest: str) -> None:
    if DRY_RUN_ENV:
        return
    sb_patch(
        int(row["id"]),
        {
            "status": "completed",
            "caminho_local": str(local_path),
            "sha256_local": digest,
            "baixado_em": "now()",
            "verificado_em": "now()",
            "removido_drive_em": "now()",
            "ultimo_erro": None,
            "atualizado_em": "now()",
        },
        expected_status="processing",
    )


def pending_rows() -> list[dict[str, Any]]:
    return sb_get(
        {
            "select": "*",
            "status": "eq.pending",
            "order": "ordem_fila.asc,id.asc",
            "limit": "500",
        }
    )


def run(dry_run: bool) -> int:
    global DRY_RUN_ENV
    DRY_RUN_ENV = dry_run

    rows = pending_rows()
    total = sum(int(r["tamanho_bytes"]) for r in rows)
    print(f"Pendentes: {len(rows)} | volume: {total} bytes")

    if total < THRESHOLD:
        print(
            f"Gate 1 GB: NÃO atingido "
            f"({total}/{THRESHOLD} bytes). Nenhum processamento."
        )
        return 0

    service = drive_service()
    consumed = 0

    for original in rows:
        size = int(original["tamanho_bytes"])
        if consumed and consumed + size > BATCH_BYTES:
            break

        row = claim(original)
        if row is None:
            print(f"ID {original['id']}: perdeu a corrida de claim; seguindo.")
            continue

        file_id = row["drive_file_id"]
        try:
            meta = drive_metadata(service, file_id)
            if meta.get("trashed"):
                raise RuntimeError("Arquivo Drive já está na lixeira.")

            name = meta["name"]
            expected_size = int(row["tamanho_bytes"])
            actual_drive_size = int(meta.get("size") or 0)
            if actual_drive_size != expected_size:
                raise RuntimeError(
                    f"Tamanho Drive divergente: esperado={expected_size}, "
                    f"Drive={actual_drive_size}"
                )

            local_path = find_unique_local_file(name)
            local_size = local_path.stat().st_size
            if local_size != expected_size:
                raise RuntimeError(
                    f"Tamanho local divergente: esperado={expected_size}, "
                    f"local={local_size}"
                )

            digest = sha256_file(local_path)
            if digest.lower() != row["drive_sha256"].lower():
                raise RuntimeError(
                    f"SHA-256 divergente para {local_path}: "
                    f"esperado={row['drive_sha256']}, local={digest}"
                )

            print(
                f"OK LOCAL | id={row['id']} | foto={row['foto_id']} | "
                f"{local_path} | sha256={digest}"
            )

            if dry_run:
                print("DRY-RUN: exclusão no Drive NÃO executada.")
            else:
                if not ALLOW_DELETE:
                    raise RuntimeError(
                        "Exclusão bloqueada: LOCAL_MIRROR_ALLOW_DELETE != true"
                    )
                service.files().delete(
                    fileId=file_id,
                    supportsAllDrives=True,
                ).execute()
                complete(row, local_path, digest)
                print(f"DRIVE REMOVIDO APÓS VERIFICAÇÃO | {file_id}")

            consumed += size

        except Exception as exc:
            print(f"FALHA | id={row['id']} | {exc}", file=sys.stderr)
            fail(row, str(exc))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="não altera o outbox e não exclui arquivos do Drive",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="permite processamento real; exclusão ainda exige ALLOW_DELETE=true",
    )
    args = parser.parse_args()

    if args.dry_run and args.live:
        parser.error("Use --dry-run ou --live, não ambos.")

    dry_run = not args.live
    return run(dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
