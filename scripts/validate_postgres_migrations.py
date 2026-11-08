"""Valida a sintaxe SQL dos schemas e migrations sem conexão ou credenciais remotas.

O parser PostgreSQL verifica a gramática SQL externa. Corpos PL/pgSQL continuam
exigindo execução em PostgreSQL/Supabase local para validação semântica completa.
"""
from __future__ import annotations

from pathlib import Path

from pglast import parse_sql
from pglast.parser import ParseError

ROOT = Path(__file__).resolve().parents[1]


def collect_sql_files(root: Path = ROOT) -> list[Path]:
    candidates = [root / "postgresql_schema.sql", root / "supabase_migration_fotos_google_sheets.sql"]
    candidates.extend(sorted((root / "supabase" / "migrations").glob("*.sql")))
    candidates.extend(sorted((root / "migrations").glob("*.sql")))
    return [path for path in candidates if path.is_file()]


def validate_sql_files(root: Path = ROOT) -> list[tuple[str, int]]:
    files = collect_sql_files(root)
    if not files:
        raise RuntimeError("Nenhum arquivo SQL foi encontrado para validação.")

    results = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        try:
            statements = parse_sql(source)
        except ParseError as exc:
            location = getattr(exc, "location", None)
            line = source.count("\n", 0, location or 0) + 1
            raise RuntimeError(f"SQL inválido em {path.relative_to(root)}:{line}: {exc}") from None
        if not statements:
            raise RuntimeError(f"Arquivo SQL vazio: {path.relative_to(root)}")
        results.append((str(path.relative_to(root)), len(statements)))
    return results


def main() -> int:
    results = validate_sql_files()
    total = sum(count for _, count in results)
    print(f"POSTGRESQL_SQL_SYNTAX_OK: files={len(results)} statements={total}")
    for name, count in results:
        print(f"SQL_FILE_OK: {name} statements={count}")
    print(
        "LIMITATION: parser valida a sintaxe SQL externa; "
        "execução semântica das migrations exige PostgreSQL/Supabase local."
    )
    return 0


if __name__ == "__main__":
    main()
