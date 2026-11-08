"""Valida a sintaxe SQL e aponta lacunas conhecidas do baseline sem credenciais remotas.

O parser PostgreSQL verifica a gramática SQL externa. Corpos PL/pgSQL continuam
exigindo execução em PostgreSQL/Supabase local para validação semântica completa.
"""
from __future__ import annotations

import re
from pathlib import Path

from pglast import parse_sql
from pglast.parser import ParseError

ROOT = Path(__file__).resolve().parents[1]


def collect_sql_files(root: Path = ROOT) -> list[Path]:
    candidates = [
        root / "postgresql_schema.sql",
        root / "supabase_migration_fotos_google_sheets.sql",
    ]
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
            raise RuntimeError(
                f"SQL inválido em {path.relative_to(root)}:{line}: {exc}"
            ) from None
        if not statements:
            raise RuntimeError(f"Arquivo SQL vazio: {path.relative_to(root)}")
        results.append((str(path.relative_to(root)), len(statements)))
    return results


def detect_clean_baseline_gaps(root: Path = ROOT) -> list[str]:
    """Identifica pré-requisitos Supabase que não estão versionados no baseline local."""
    files = collect_sql_files(root)
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    gaps = []

    required_tables = (
        "movimentacoes_patrimonio",
        "patrimonio_fotos_sheets_outbox",
    )
    for table in required_tables:
        pattern = (
            r"create\s+table\s+(?:if\s+not\s+exists\s+)?"
            r"(?:public\.)?" + re.escape(table) + r"\b"
        )
        if not re.search(pattern, source, flags=re.IGNORECASE):
            gaps.append(
                f"baseline SQL não declara a tabela public.{table}, "
                "embora código/migrations dependam dela"
            )

    view_pattern = (
        r"create\s+(?:or\s+replace\s+)?view\s+"
        r"(?:public\.)?patrimonios_sheets_outbox_health\b"
    )
    if not re.search(view_pattern, source, flags=re.IGNORECASE):
        gaps.append(
            "baseline SQL não declara a view public.patrimonios_sheets_outbox_health"
        )

    if not (root / "supabase" / "config.toml").is_file():
        gaps.append(
            "supabase/config.toml ausente; não há configuração versionada "
            "para iniciar o Supabase local com supabase start/db reset"
        )
    return gaps


def main() -> int:
    results = validate_sql_files()
    total = sum(count for _, count in results)
    print(f"POSTGRESQL_SQL_SYNTAX_OK: files={len(results)} statements={total}")
    for name, count in results:
        print(f"SQL_FILE_OK: {name} statements={count}")

    gaps = detect_clean_baseline_gaps()
    if gaps:
        print("CLEAN_DATABASE_REPLAY: BLOCKED_BY_BASELINE_GAPS")
        for gap in gaps:
            print(f"::warning::{gap}")
    else:
        print("CLEAN_DATABASE_REPLAY: baseline prerequisites detected")

    print(
        "LIMITATION: parser valida a sintaxe SQL externa; "
        "execução semântica das migrations exige PostgreSQL/Supabase local."
    )
    return 0


if __name__ == "__main__":
    main()
