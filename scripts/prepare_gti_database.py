import os
import re
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
    host = value.strip()
    if host.endswith(f":{POOLER_PORT}"):
        host = host[: -(len(str(POOLER_PORT)) + 1)]
    return host


def _validate_shape(host: str, user: str, dbname: str) -> str:
    normalized_host = _normalize_pooler_host(host)
    if not re.fullmatch(r"aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com", normalized_host):
        raise SystemExit(
            "GTI_DB_HOST inválido: use o host do Transaction pooler copiado no "
            "Connect do Supabase. É aceito o host puro ou o host seguido de :6543; "
            "não use URL completa nem componha o host manualmente."
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
