import os
import psycopg


REQUIRED = (
    "GTI_DB_HOST",
    "GTI_DB_PORT",
    "GTI_DB_NAME",
    "GTI_DB_USER",
    "GTI_DB_PASSWORD",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "GOOGLE_SPREADSHEET_ID",
)


def main():
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Secrets GTI ausentes: " + ", ".join(missing))

    try:
        port = int(os.environ["GTI_DB_PORT"])
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit("GTI_DB_PORT inválido; informe uma porta PostgreSQL válida.") from None

    params = {
        "host": os.environ["GTI_DB_HOST"].strip(),
        "port": port,
        "dbname": os.environ["GTI_DB_NAME"].strip(),
        "user": os.environ["GTI_DB_USER"].strip(),
        "password": os.environ["GTI_DB_PASSWORD"],
        "sslmode": "require",
    }

    try:
        print(
            "Teste PostgreSQL: "
            f"host={params['host']}, port={params['port']}, "
            f"database={params['dbname']}, user_configured={bool(params['user'])}."
        )
        with psycopg.connect(**params, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except Exception as exc:
        sqlstate = getattr(exc, "sqlstate", None)
        diagnostic = type(exc).__name__
        if sqlstate:
            diagnostic += f"/SQLSTATE={sqlstate}"
        raise SystemExit(
            "Conexão PostgreSQL não pôde ser validada; diagnóstico seguro: "
            + diagnostic
        ) from None

    print("Conexão PostgreSQL validada sem exibir valores sensíveis.")


if __name__ == "__main__":
    main()
