import os
import re
from urllib.parse import urlsplit

from psycopg.conninfo import make_conninfo


PROJECT_REF = "vgabxdprocwmpmhoxrgt"
REQUIRED = (
    "GTI_DB_HOST",
    "GTI_DB_NAME",
    "GTI_DB_USER",
    "GTI_DB_PASSWORD",
)
POOLER_PORT = 6543


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
    if not re.fullmatch(r"[a-z0-9-]+\.pooler\.supabase\.com", normalized_host):
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
            "GTI_DB_NAME inválido: use o banco postgres."
        )
    return normalized_host


def main():
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Secrets PostgreSQL ausentes: " + ", ".join(missing))

    configured_host = os.environ["GTI_DB_HOST"].strip()
    dbname = os.environ["GTI_DB_NAME"].strip()
    user = os.environ["GTI_DB_USER"].strip()
    host = _validate_shape(configured_host, user, dbname)

    value = make_conninfo(
        host=host,
        port=POOLER_PORT,
        dbname=dbname,
        user=user,
        password=os.environ["GTI_DB_PASSWORD"],
        sslmode="require",
    )
    print("::add-mask::" + value)
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env_file:
        env_file.write("DATABASE_URL=" + value + "\n")
    print(
        "Conexão PostgreSQL preparada com endpoint seguro do pooler: "
        f"host={host}, port={POOLER_PORT}, database={dbname}, "
        "user_configured=True."
    )


if __name__ == "__main__":
    main()
