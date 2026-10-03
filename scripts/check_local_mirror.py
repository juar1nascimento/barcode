"""Pré-validação segura do espelhamento local do Inventário GTI SESA.

Não grava dados de inventário nem altera o PostgreSQL/Supabase.
Apenas valida o destino local, configuração e conectividade operacional.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import tempfile
from pathlib import Path

import psycopg
import requests
from psycopg.rows import dict_row
from psycopg import sql

DEFAULT_ROOT = r"\\172.17.27.246\t.i\02 - SUPORTE\BACKUP\Inventário gti-sesa"
REQUIRED_TABLES = (
    "patrimonios",
    "unidades",
    "setores",
    "movimentacoes_patrimonio",
    "patrimonio_fotos",
)
TIMEOUT = int(os.getenv("INVENTARIO_MIRROR_PREFLIGHT_TIMEOUT", "15"))


def _configured_db() -> bool:
    return bool(os.getenv("DATABASE_URL")) or all(
        os.getenv(name)
        for name in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")
    )


def _db_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg.connect(
            database_url, connect_timeout=TIMEOUT, row_factory=dict_row
        )
    return psycopg.connect(
        host=os.environ["PGHOST"],
        port=os.getenv("PGPORT", "5432"),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode=os.getenv("PGSSLMODE", "require"),
        connect_timeout=TIMEOUT,
        row_factory=dict_row,
    )


def _check_local(root: Path) -> list[str]:
    errors: list[str] = []
    if not root.exists():
        errors.append(f"Destino não acessível: {root}")
        return errors
    if not root.is_dir():
        errors.append(f"Destino não é uma pasta: {root}")
        return errors

    try:
        with tempfile.NamedTemporaryFile(
            prefix=".inventario-preflight-",
            suffix=".tmp",
            dir=root,
            delete=False,
        ) as handle:
            probe = Path(handle.name)
            handle.write(b"Inventario GTI SESA preflight")
            handle.flush()
        probe.unlink()
    except Exception as exc:
        errors.append("Destino sem permissão de escrita.")

    return errors


def _check_database() -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    counts: dict[str, int] = {}
    if not _configured_db():
        return ["DATABASE_URL ou PGHOST/PGDATABASE/PGUSER/PGPASSWORD não configurado."], counts

    try:
        with _db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select table_name from information_schema.tables "
                    "where table_schema='public' and table_name = any(%s)",
                    [list(REQUIRED_TABLES)],
                )
                found = {str(row["table_name"]) for row in cur.fetchall()}
                missing = [name for name in REQUIRED_TABLES if name not in found]
                if missing:
                    errors.append("Tabelas ausentes: " + ", ".join(missing))
                    return errors, counts

                for table in REQUIRED_TABLES:
                    cur.execute(sql.SQL("select count(*) as total from public.{}").format(sql.Identifier(table)))
                    counts[table] = int(cur.fetchone()["total"])
    except Exception as exc:
        errors.append("PostgreSQL indisponível ou credenciais inválidas.")

    return errors, counts


def _check_storage() -> list[str]:
    errors: list[str] = []
    base_url = str(os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    service_key = str(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not base_url:
        return ["SUPABASE_URL não configurado."]
    if not service_key:
        return ["SUPABASE_SERVICE_ROLE_KEY não configurado no ambiente seguro do servidor."]

    try:
        response = requests.get(
            f"{base_url}/storage/v1/bucket",
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
                "User-Agent": "Inventario-GTI-SESA-Preflight/1.0",
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        errors.append("Supabase Storage indisponível ou credencial inválida.")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Valida somente o servidor/pasta local, sem acessar PostgreSQL ou Storage.",
    )
    args = parser.parse_args()

    root = Path(os.getenv("INVENTARIO_MIRROR_ROOT", DEFAULT_ROOT))
    print("Inventário GTI SESA - PRE-FLIGHT")
    print(f"Servidor: {platform.node()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Destino: {root}")

    failures = _check_local(root)
    if failures:
        for item in failures:
            print(f"[ERRO] {item}")
    else:
        print("[OK] Pasta local acessível e com escrita temporária.")

    if sys.version_info < (3, 12):
        failures.append("Python 3.12 ou superior é necessário para o ambiente de produção.")
    else:
        print("[OK] Python 3.12+.")

    if not args.local_only:
        db_errors, counts = _check_database()
        for item in db_errors:
            print(f"[ERRO] {item}")
        if not db_errors:
            print("[OK] PostgreSQL conectado e schema operacional encontrado.")
            print("[INFO] Contagens:", counts)

        storage_errors = _check_storage()
        for item in storage_errors:
            print(f"[ERRO] {item}")
        if not storage_errors:
            print("[OK] Supabase Storage acessível.")

        failures.extend(db_errors)
        failures.extend(storage_errors)

    if failures:
        print(f"[BLOQUEADO] Pré-validação encontrou {len(failures)} problema(s).")
        return 2

    print("[APROVADO] Ambiente pronto para a próxima etapa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
