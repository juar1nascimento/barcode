import os
import re

import psycopg


REQUIRED = (
    "GTI_DB_HOST",
    "GTI_DB_NAME",
    "GTI_DB_USER",
    "GTI_DB_PASSWORD",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "GOOGLE_SPREADSHEET_ID",
)

POOLER_HOST = "aws-0-sa-east-1.pooler.supabase.com"
POOLER_PORT = 6543
DIRECT_PORT = 5432


def _host_candidates(configured_host: str):
    candidates = [(configured_host, POOLER_PORT)]
    if configured_host.startswith("db."):
        candidates.insert(0, (POOLER_HOST, POOLER_PORT))
        candidates.append((configured_host, DIRECT_PORT))
    return list(dict.fromkeys(candidates))


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(r"(?i)(password=)[^ ]+", r"\1***", message)
    message = re.sub(r"(?i)(postgres(?:ql)?://)[^ ]+", r"\1***", message)
    message = re.sub(r"\s+", " ", message).strip()
    return message[:300] or type(exc).__name__


def main():
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Secrets GTI ausentes: " + ", ".join(missing))

    configured_host = os.environ["GTI_DB_HOST"].strip()
    base = {
        "dbname": os.environ["GTI_DB_NAME"].strip(),
        "user": os.environ["GTI_DB_USER"].strip(),
        "password": os.environ["GTI_DB_PASSWORD"],
        "sslmode": "require",
        "connect_timeout": 8,
    }

    failures = []
    for host, port in _host_candidates(configured_host):
        params = {**base, "host": host, "port": port}
        try:
            print(
                "Teste PostgreSQL: "
                f"endpoint={host}:{port}, database={params['dbname']}, "
                f"user_configured={bool(params['user'])}."
            )
            with psycopg.connect(**params) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            print(
                "Conexão PostgreSQL validada sem exibir valores sensíveis; "
                f"endpoint={host}:{port}."
            )
            return
        except Exception as exc:
            sqlstate = getattr(exc, "sqlstate", None)
            diagnostic = type(exc).__name__
            if sqlstate:
                diagnostic += f"/SQLSTATE={sqlstate}"
            failures.append(f"{host}:{port} -> {diagnostic}: {_safe_error(exc)}")

    raise SystemExit(
        "Conexão PostgreSQL não pôde ser validada. Diagnósticos seguros: "
        + " | ".join(failures)
    )


if __name__ == "__main__":
    main()
