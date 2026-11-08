import pytest

from scripts import validate_postgres_connection as validator


def _env(**overrides):
    values = {
        "GTI_DB_HOST": "aws-0-us-east-1.pooler.supabase.com",
        "GTI_DB_NAME": "postgres",
        "GTI_DB_USER": "postgres.vgabxdprocwmpmhoxrgt",
        "GTI_DB_PASSWORD": "not-a-real-secret",
    }
    values.update(overrides)
    return values


def test_postgres_config_does_not_require_google_credentials():
    result = validator.validate_config(_env())
    assert result["dbname"] == "postgres"
    assert result["host"].endswith(".pooler.supabase.com")


def test_postgres_config_reports_missing_database_variables():
    with pytest.raises(validator.ValidationError, match="GTI_DB_PASSWORD"):
        validator.validate_config(_env(GTI_DB_PASSWORD=""))


def test_postgres_config_rejects_non_pooler_host():
    with pytest.raises(validator.ValidationError, match="GTI_DB_HOST"):
        validator.validate_config(_env(GTI_DB_HOST="db.example.com"))


def test_postgres_connection_forces_read_only_session():
    calls = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query):
            calls["query"] = query

        def fetchone(self):
            return (1, "on")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    def connector(**kwargs):
        calls["kwargs"] = kwargs
        return Connection()

    validator.validate_connection(_env(), connector=connector)
    assert "default_transaction_read_only=on" in calls["kwargs"]["options"]
    assert calls["query"].startswith("SELECT 1")
