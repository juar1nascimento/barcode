from scripts.validate_postgres_migrations import (
    detect_clean_baseline_gaps,
    validate_sql_files,
)


def test_all_repository_sql_files_parse_with_postgresql_grammar():
    results = validate_sql_files()
    assert results
    assert any(name == "postgresql_schema.sql" for name, _ in results)
    assert any(name.startswith("supabase/migrations/") for name, _ in results)
    assert all(statement_count > 0 for _, statement_count in results)


def test_validator_reports_incomplete_clean_database_baseline():
    gaps = detect_clean_baseline_gaps()
    assert any("movimentacoes_patrimonio" in gap for gap in gaps)
    assert any("patrimonio_fotos_sheets_outbox" in gap for gap in gaps)
    assert any("supabase/config.toml" in gap for gap in gaps)
