import os
from psycopg.conninfo import make_conninfo


REQUIRED = (
    "GTI_DB_HOST",
    "GTI_DB_NAME",
    "GTI_DB_USER",
    "GTI_DB_PASSWORD",
)

POOLER_HOST = "aws-0-sa-east-1.pooler.supabase.com"
POOLER_PORT = 6543


def main():
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Secrets PostgreSQL ausentes: " + ", ".join(missing))

    configured_host = os.environ["GTI_DB_HOST"].strip()
    host = POOLER_HOST if configured_host.startswith("db.") else configured_host

    value = make_conninfo(
        host=host,
        port=POOLER_PORT,
        dbname=os.environ["GTI_DB_NAME"].strip(),
        user=os.environ["GTI_DB_USER"].strip(),
        password=os.environ["GTI_DB_PASSWORD"],
        sslmode="require",
    )
    print("::add-mask::" + value)
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env_file:
        env_file.write("DATABASE_URL=" + value + "\n")
    print(
        "Conexão PostgreSQL preparada com endpoint seguro do pooler: "
        f"host={host}, port={POOLER_PORT}, "
        f"database={os.environ['GTI_DB_NAME'].strip()}, "
        f"user_configured={bool(os.environ['GTI_DB_USER'].strip())}."
    )


if __name__ == "__main__":
    main()
