from datetime import datetime, timezone
from decimal import Decimal

import pytest

import projecao_almoxarifado_sheets_worker as worker


class FakeCursor:
    def __init__(self, statements):
        self.statements = statements
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query):
        self.statements.append(" ".join(query.split()))
        if "v_projecao_almoxarifado_central_resumo" in query:
            self.rows = [(2, "Almoxarifado Central SESA", 1, 1, 10, 4, 6, 0, 0, 1, Decimal("40.00"), None)]
        elif "v_projecao_almoxarifado_central" in query:
            self.rows = [(1, 2, "Almoxarifado Central SESA", "CPU", None, "Dell", 10, 4, 6, Decimal("40.00"), "EM_ANDAMENTO", None)]
        else:
            self.rows = []

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self):
        self.statements = []
        self.closed = False

    def cursor(self):
        return FakeCursor(self.statements)

    def close(self):
        self.closed = True


def test_dry_run_uses_read_only_transaction_and_never_opens_google(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(worker.psycopg, "connect", lambda _dsn: connection)
    monkeypatch.setattr(worker, "database_url", lambda: "test-dsn")

    def forbidden(*_args, **_kwargs):
        pytest.fail("O modo dry-run não pode acessar nem escrever no Google Sheets.")

    monkeypatch.setattr(worker, "sheets_client", forbidden)
    monkeypatch.setattr(worker, "open_spreadsheet", forbidden)
    monkeypatch.setattr(worker, "sync_sheet", forbidden)

    result = worker.run(dry_run=True)

    assert connection.closed is True
    assert connection.statements[0] == "SET TRANSACTION READ ONLY"
    assert all(statement.startswith(("SET TRANSACTION READ ONLY", "SELECT ")) for statement in connection.statements)
    assert result["result"] == "validated_read_only"
    assert result["database_transaction"] == "READ ONLY"
    assert result["google_sheets_connected"] is False
    assert result["external_write"] is False
    assert result["abas"][0]["linhas"] == 1
    assert result["abas"][1]["linhas"] == 1


def test_sync_sheet_does_not_clear_sheet_for_empty_snapshot():
    class ForbiddenSpreadsheet:
        def worksheet(self, _name):
            pytest.fail("Snapshot vazio não deve sequer abrir a planilha.")

    result = worker.sync_sheet(
        ForbiddenSpreadsheet(),
        [worker.COLUMNS],
        worker.DETAIL_SHEET_NAME,
        worker.COLUMNS,
    )

    assert result["status"] == "skipped_empty_snapshot"
    assert result["linhas"] == 0


def test_sync_sheet_rejects_malformed_snapshot_before_touching_sheet():
    class ForbiddenSpreadsheet:
        def worksheet(self, _name):
            pytest.fail("Snapshot inválido não deve acessar a planilha.")

    with pytest.raises(ValueError, match="quantidade de colunas divergente"):
        worker.sync_sheet(
            ForbiddenSpreadsheet(),
            [worker.COLUMNS, ["incomplete"]],
            worker.DETAIL_SHEET_NAME,
            worker.COLUMNS,
        )


def test_sync_sheet_rejects_header_mismatch_before_touching_sheet():
    class ForbiddenSpreadsheet:
        def worksheet(self, _name):
            pytest.fail("Cabeçalho divergente não deve acessar a planilha.")

    with pytest.raises(ValueError, match="cabeçalho ausente ou divergente"):
        worker.sync_sheet(
            ForbiddenSpreadsheet(),
            [["header errado"]],
            worker.DETAIL_SHEET_NAME,
            worker.COLUMNS,
        )


def test_normalize_value_handles_datetime_and_decimal():
    moment = datetime(2026, 11, 16, 12, 30, tzinfo=timezone.utc)

    assert worker.normalize_value(moment) == "2026-11-16 12:30:00+00:00"
    assert worker.normalize_value(Decimal("12.0")) == 12
    assert worker.normalize_value(Decimal("12.5")) == 12.5
    assert worker.normalize_value(Decimal("NaN")) is None


@pytest.mark.parametrize(
    ("number", "expected"),
    [(1, "A"), (26, "Z"), (27, "AA"), (52, "AZ"), (702, "ZZ"), (703, "AAA")],
)
def test_column_letter(number, expected):
    assert worker.column_letter(number) == expected



def test_safe_error_redacts_database_passwords_and_tokens():
    message = worker.safe_error(
        "connection failed password=database-secret token=jwt-secret"
    )

    assert "database-secret" not in message
    assert "jwt-secret" not in message
    assert "password=[REDACTED]" in message
    assert "token=[REDACTED]" in message
