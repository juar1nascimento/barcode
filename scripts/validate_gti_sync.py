import os
import psycopg
from psycopg.conninfo import conninfo_to_dict


def main():
    required = [
        "DATABASE_URL",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_SPREADSHEET_ID",
    ]
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Secrets GTI ausentes: " + ", ".join(missing))

    database = os.environ["DATABASE_URL"].strip()
    try:
        params = conninfo_to_dict(database)
    except Exception as exc:
        raise SystemExit(
            "GTI_DATABASE_URL possui formato inválido; use uma URI PostgreSQL válida. "
            "Tipo técnico: " + type(exc).__name__ + "."
        ) from None

    host = params.get("host", "")
    if not host:
        raise SystemExit(
            "GTI_DATABASE_URL possui formato inválido; informe o host PostgreSQL."
        )

    candidates = [("primary", params)]
    project_ref = ""
    if host.startswith("db.") and host.endswith(".supabase.co"):
        project_ref = host[3:-len(".supabase.co")]

    if project_ref:
        pooler_params = dict(params)
        if pooler_params.get("user") == "postgres":
            pooler_params["user"] = f"postgres.{project_ref}"
        pooler_params["host"] = os.environ["SUPABASE_POOLER_HOST"]
        pooler_params["port"] = 6543
        candidates.append(("supabase-pooler", pooler_params))

    failures = []
    for label, candidate in candidates:
        try:
            print(
                f"Teste PostgreSQL [{label}]: "
                f"host={candidate.get('host')}, "
                f"port={candidate.get('port', 5432)}, "
                f"database={candidate.get('dbname', 'postgres')}, "
                f"user_configured={bool(candidate.get('user'))}."
            )
            with psycopg.connect(**candidate, connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            if label == "supabase-pooler":
                print("Conexão PostgreSQL validada pelo pooler IPv4 do Supabase.")
            else:
                print("Conexão PostgreSQL validada sem exibir valores sensíveis.")
            return
        except Exception as exc:
            sqlstate = getattr(exc, "sqlstate", None)
            failures.append(
                f"{label}:{type(exc).__name__}"
                + (f"/SQLSTATE={sqlstate}" if sqlstate else "")
            )

    raise SystemExit(
        "GTI_DATABASE_URL não pôde ser conectada; diagnóstico seguro: "
        + ", ".join(failures)
    )


if __name__ == "__main__":
    main()
