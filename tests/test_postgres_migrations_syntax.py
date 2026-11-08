from scripts.validate_postgres_migrations import validate_sql_files


def test_all_repository_sql_files_parse_with_postgresql_grammar():
    results = validate_sql_files()
    assert results
    assert any(name == "postgresql_schema.sql" for name, _ in results)
    assert any(name.startswith("supabase/migrations/") for name, _ in results)
    assert all(statement_count > 0 for _, statement_count in results)
