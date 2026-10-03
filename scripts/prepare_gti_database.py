import os
from psycopg.conninfo import make_conninfo


REQUIRED = (
    "GTI_DB_HOST",
    "GTI_DB_PORT",
    "GTI_DB_NAME",
    "GTI_DB_USER",
    "GTI_DB_PASSWORD",
)


def main():
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Secrets PostgreSQL ausentes: " + ", ".join(missing))

    try:
        port = int(os.environ["GTI_DB_PORT"])
        if not 1 <= port <= 65535:
            raise ValueError("porta fora do intervalo")
    except ValueError:
        raise SystemExit("GTI_DB_PORT inválido; informe uma porta PostgreSQL válida.") from None

    value = make_conninfo(
        host=os.environ["GTI_DB_HOST"].strip(),
        port=port,
        dbname=os.environ["GTI_DB_NAME"].strip(),
        user=os.environ["GTI_DB_USER"].strip(),
        password=os.environ["GTI_DB_PASSWORD"],
        sslmode="require",
    )
    print("::add-mask::" + value)
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env_file:
        env_file.write("DATABASE_URL=" + value + "\n")
    print(
        "Conexão PostgreSQL preparada com secrets separados: "
        f"host={os.environ['GTI_DB_HOST'].strip()}, port={port}, "
        f"database={os.environ['GTI_DB_NAME'].strip()}, "
        f"user_configured={bool(os.environ['GTI_DB_USER'].strip())}."
    )


if __name__ == "__main__":
    main()
