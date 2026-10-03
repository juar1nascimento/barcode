import os
from psycopg.conninfo import make_conninfo


PROJECT_REF = "vgabxdprocwmpmhoxrgt"
REQUIRED = (
    "GTI_DB_HOST",
    "GTI_DB_NAME",
    "GTI_DB_USER",
    "GTI_DB_PASSWORD",
)
POOLER_PORT = 6543


def _validate_shape(host: str, user: str, dbname: str) -> None:
    import re

    if not re.fullmatch(r"aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com", host):
        raise SystemExit(
            "GTI_DB_HOST inválido: use exatamente o host do Transaction pooler "
            "copiado no Connect do Supabase."
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


def main():
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Secrets PostgreSQL ausentes: " + ", ".join(missing))

    host = os.environ["GTI_DB_HOST"].strip()
    dbname = os.environ["GTI_DB_NAME"].strip()
    user = os.environ["GTI_DB_USER"].strip()
    _validate_shape(host, user, dbname)

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
