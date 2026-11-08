"""Validação PostgreSQL/Supabase independente, estritamente somente leitura.

Usa somente GTI_DB_*; não exige credenciais do Google Sheets e nunca grava dados.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

import psycopg

PROJECT_REF = os.getenv("GTI_SUPABASE_PROJECT_REF", "vgabxdprocwmpmhoxrgt")
POOLER_PORT = 6543
REQUIRED = ("GTI_DB_HOST", "GTI_DB_NAME", "GTI_DB_USER", "GTI_DB_PASSWORD")
POOLER_RE = re.compile(r"^aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com$")


class ValidationError(ValueError):
    """Configuração inválida ou incompleta, sem conteúdo secreto."""


def validate_config(environ=None) -> dict[str, str]:
    env = os.environ if environ is None else environ
    missing = [key for key in REQUIRED if not str(env.get(key, "")).strip()]
    if missing:
        raise ValidationError("Variáveis PostgreSQL ausentes: " + ", ".join(missing))

    raw_host = str(env["GTI_DB_HOST"]).strip()
    if "://" in raw_host:
        host = urlsplit(raw_host).hostname or ""
    else:
        host = raw_host.rsplit("@", 1)[-1].split("/", 1)[0]
        if host.count(":") == 1:
            host = host.rsplit(":", 1)[0]
    host = host.rstrip(".").lower()

    if not POOLER_RE.fullmatch(host):
        raise ValidationError(
            "GTI_DB_HOST inválido: informe o hostname Transaction Pooler "
            "fornecido pelo Connect do Supabase."
        )
    dbname = str(env["GTI_DB_NAME"]).strip()
    user = str(env["GTI_DB_USER"]).strip()
    if dbname != "postgres":
        raise ValidationError("GTI_DB_NAME deve ser postgres para este validador.")
    if user != f"postgres.{PROJECT_REF}":
        raise ValidationError(
            "GTI_DB_USER não corresponde ao projeto Supabase configurado."
        )

    return {
        "host": host,
        "dbname": dbname,
        "user": user,
        "password": str(env["GTI_DB_PASSWORD"]),
    }


def validate_connection(environ=None, connector=None) -> dict[str, str]:
    config = validate_config(environ)
    connect = connector or psycopg.connect
    with connect(
        host=config["host"],
        port=POOLER_PORT,
        dbname=config["dbname"],
        user=config["user"],
        password=config["password"],
        sslmode="require",
        connect_timeout=8,
        options="-c default_transaction_read_only=on",
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1, current_setting('transaction_read_only')")
            row = cur.fetchone()
            if row != (1, "on"):
                raise ValidationError(
                    "PostgreSQL respondeu, mas a sessão não confirmou modo somente leitura."
                )
    return {"host": config["host"], "database": config["dbname"]}


def main() -> int:
    try:
        result = validate_connection()
    except ValidationError as exc:
        raise SystemExit(str(exc)) from None
    except Exception as exc:
        sqlstate = getattr(exc, "sqlstate", None)
        detail = type(exc).__name__ + (f"/SQLSTATE={sqlstate}" if sqlstate else "")
        raise SystemExit(
            "Validação PostgreSQL falhou; diagnóstico sem dados sensíveis: " + detail
        ) from None
    print(
        "POSTGRESQL_VALIDATION_OK: "
        f"host={result['host']} database={result['database']} read_only=true"
    )
    return 0


if __name__ == "__main__":
    main()
