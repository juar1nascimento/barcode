import os
import re
from urllib.parse import urlsplit

import psycopg


PROJECT_REF = "vgabxdprocwmpmhoxrgt"
REQUIRED = (
    "GTI_DB_HOST",
    "GTI_DB_NAME",
    "GTI_DB_USER",
    "GTI_DB_PASSWORD",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "GOOGLE_SPREADSHEET_ID",
)
POOLER_PORT = 6543


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(r"(?i)(password=)[^ ]+", r"\\1***", message)
    message = re.sub(r"(?i)(postgres(?:ql)?://)[^ ]+", r"\\1***", message)
    message = re.sub(r"\\s+", " ", message).strip()
    return message[:300] or type(exc).__name__


def _normalize_pooler_host(value: str) -> str:
    raw = value.strip()
    if "://" in raw:
        parsed = urlsplit(raw)
        host = parsed.hostname or ""
    else:
        host = raw.rsplit("@", 1)[-1].split("/", 1)[0]
        if host.count(":") == 1:
            host = host.rsplit(":", 1)[0]
    return host.rstrip(".").lower()


def _validate_shape(host: str, user: str, dbname: str) -> str:
    normalized_host = _normalize_pooler_host(host)
    if not re.fullmatch(r"aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com", normalized_host):
        raise SystemExit(
            "GTI_DB_HOST inválido: informe o endpoint do Transaction pooler do "
            "Connect do Supabase. O validador aceita host puro, host:porta ou "
            "connection string PostgreSQL, mas não aceita outro endpoint."
        )
    if user != f"postgres.{PROJECT_REF}":
        raise SystemExit(
            "GTI_DB_USER inválido para o shared pooler: use o usuário completo "
            "fornecido pelo Connect do Supabase."
        )
    if dbname != "postgres":
        raise SystemExit(
            "GTI_DB_NAME inválido: a conexão do pooler deste workflow deve usar "
            "o banco postgres."
        )
    return normalized_host


def main():
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Secrets GTI ausentes: " + ", ".join(missing))

    configured_host = os.environ["GTI_DB_HOST"].strip()
    configured_user = os.environ["GTI_DB_USER"].strip()
    configured_dbname = os.environ["GTI_DB_NAME"].strip()
    normalized_host = _validate_shape(
        configured_host, configured_user, configured_dbname
    )

    params = {
        "host": normalized_host,
        "port": POOLER_PORT,
        "dbname": configured_dbname,
        "user": configured_user,
        "password": os.environ["GTI_DB_PASSWORD"],
        "sslmode": "require",
        "connect_timeout": 8,
    }
    try:
        print(
            "Teste PostgreSQL: "
            f"endpoint={normalized_host}:{POOLER_PORT}, "
            f"database={configured_dbname}, user_configured=True."
        )
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        print(
            "Conexão PostgreSQL validada sem exibir valores sensíveis; "
            f"endpoint={normalized_host}:{POOLER_PORT}."
        )
    except Exception as exc:
        sqlstate = getattr(exc, "sqlstate", None)
        diagnostic = type(exc).__name__
        if sqlstate:
            diagnostic += f"/SQLSTATE={sqlstate}"
        raise SystemExit(
            "Conexão PostgreSQL não pôde ser validada. "
            f"Diagnóstico seguro: {diagnostic}: {_safe_error(exc)}"
        ) from None


if __name__ == "__main__":
    main()
