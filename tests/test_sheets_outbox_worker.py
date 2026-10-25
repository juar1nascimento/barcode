from types import SimpleNamespace

import pytest

import sheets_outbox_worker as worker


class ApiError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.response = SimpleNamespace(status_code=status_code)


def test_sheets_call_returns_success_value():
    assert worker._sheets_call("test", lambda: "ok") == "ok"


def test_sheets_call_retries_transient_google_error(monkeypatch):
    calls = {"count": 0}
    monkeypatch.setattr(worker.time, "sleep", lambda _seconds: None)

    def callback():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ApiError(503)
        return "recovered"

    assert worker._sheets_call("test_retry", callback, attempts=3) == "recovered"
    assert calls["count"] == 3


def test_sheets_call_does_not_retry_permanent_client_error(monkeypatch):
    calls = {"count": 0}
    monkeypatch.setattr(worker.time, "sleep", lambda _seconds: None)

    def callback():
        calls["count"] += 1
        raise ApiError(400)

    with pytest.raises(RuntimeError, match="Google Sheets operation test_bad_request failed"):
        worker._sheets_call("test_bad_request", callback, attempts=4)

    assert calls["count"] == 1



def test_defer_dependency_requeues_without_consuming_attempts():
    class FakeCursor:
        def __init__(self):
            self.query = ""
            self.params = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            self.query = query
            self.params = params

    class FakeConnection:
        def __init__(self):
            self.fake_cursor = FakeCursor()
            self.commits = 0

        def cursor(self):
            return self.fake_cursor

        def commit(self):
            self.commits += 1

    conn = FakeConnection()
    worker.defer_dependency(conn, 17, "Drive URL not ready")

    query = " ".join(conn.fake_cursor.query.split())
    assert "SET status='pending'" in query
    assert "tentativas=GREATEST(tentativas - 1, 0)" in query
    assert "interval '5 minutes'" in query
    assert conn.fake_cursor.params == ("Drive URL not ready", 17)
    assert conn.commits == 1


def test_missing_drive_url_is_classified_as_dependency_not_permanent_failure():
    assert issubclass(worker.DependencyNotReady, RuntimeError)



def test_locates_photo_row_by_stable_id_when_number_is_duplicated():
    header = [
        "Setor", "Tipo de Patrimônio", "Nº de Patrimônio",
        "Fabricante", "Data Cadastro", "Código de Barras", worker.ID_COLUMN,
    ]
    values = [
        header,
        ["Sala A", "CPU", "PAT-01", "Fab A", "", "", "101"],
        ["Sala B", "CPU", "PAT-01", "Fab B", "", "", "202"],
    ]
    assert worker.locate_patrimony_row(header, values, 202, "PAT-01", "Unidade A") == 3


def test_falls_back_to_unique_number_only_when_stable_id_is_blank():
    header = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", worker.ID_COLUMN]
    values = [header, ["Sala A", "CPU", "PAT-02", ""]]
    assert worker.locate_patrimony_row(header, values, 303, "PAT-02", "Unidade A") == 2


def test_blocks_missing_photo_parent_row_for_controlled_reconciliation():
    header = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", worker.ID_COLUMN]
    values = [header, ["Sala A", "CPU", "PAT-03", "303"]]
    with pytest.raises(worker.ReconciliationRequired, match="reconciliação controlada"):
        worker.locate_patrimony_row(header, values, 404, "PAT-04", "Unidade A")


def test_blocks_number_fallback_when_existing_id_conflicts():
    header = ["Setor", "Tipo de Patrimônio", "Nº de Patrimônio", worker.ID_COLUMN]
    values = [header, ["Sala A", "CPU", "PAT-04", "999"]]
    with pytest.raises(worker.ReconciliationRequired, match="informa ID 505"):
        worker.locate_patrimony_row(header, values, 505, "PAT-04", "Unidade A")


def test_blocks_duplicate_stable_id():
    header = ["Nº de Patrimônio", worker.ID_COLUMN]
    values = [header, ["PAT-05", "606"], ["PAT-06", "606"]]
    with pytest.raises(worker.ReconciliationRequired, match="ID Patrimônio 606 duplicado"):
        worker.locate_patrimony_row(header, values, 606, "PAT-05", "Unidade A")


def test_mark_dead_letter_sets_permanent_block_without_retry_schedule():
    class FakeCursor:
        def __init__(self):
            self.query = ""
            self.params = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            self.query = query
            self.params = params

    class FakeConnection:
        def __init__(self):
            self.fake_cursor = FakeCursor()
            self.commits = 0

        def cursor(self):
            return self.fake_cursor

        def commit(self):
            self.commits += 1

    conn = FakeConnection()
    worker.mark(conn, 36, "dead_letter", "row missing", max_attempts=12)
    query = " ".join(conn.fake_cursor.query.split())
    assert "SET status='dead_letter'" in query
    assert "proxima_tentativa_em=now()" in query
    assert conn.fake_cursor.params == ("row missing", 36)
    assert conn.commits == 1


def test_count_dead_letter_is_read_only_and_returns_count():
    class FakeCursor:
        def __init__(self):
            self.query = ""
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, query):
            self.query = query
        def fetchone(self):
            return (2,)

    class FakeConnection:
        def __init__(self):
            self.fake_cursor = FakeCursor()
        def cursor(self):
            return self.fake_cursor

    conn = FakeConnection()
    assert worker.count_dead_letter(conn) == 2
    assert conn.fake_cursor.query.strip().startswith("SELECT count(*)")
    assert "status='dead_letter'" in conn.fake_cursor.query



def test_blocks_missing_photo_columns_for_controlled_reconciliation():
    header = ["Nº de Patrimônio", worker.ID_COLUMN] + [f"Foto {n:02d}" for n in range(1, 10)]
    with pytest.raises(worker.ReconciliationRequired, match="coluna Foto 10 ausente"):
        worker.locate_photo_columns(header, "Unidade A")


def test_blocks_ambiguous_legacy_and_canonical_photo_columns():
    header = ["Nº de Patrimônio", worker.ID_COLUMN] + [
        "Foto 1", "Foto 01", *[f"Foto {n:02d}" for n in range(2, 11)]
    ]
    with pytest.raises(worker.ReconciliationRequired, match="coluna Foto 1 ambígua/duplicada"):
        worker.locate_photo_columns(header, "Unidade A")



def test_missing_parent_row_is_deferred_when_inventory_outbox_is_not_terminal():
    class FakeCursor:
        def __init__(self):
            self.query = ""
            self.params = None
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, query, params):
            self.query = query
            self.params = params
        def fetchone(self):
            return ("pending",)

    class FakeConnection:
        def __init__(self):
            self.fake_cursor = FakeCursor()
        def cursor(self):
            return self.fake_cursor

    conn = FakeConnection()
    header = ["Nº de Patrimônio", worker.ID_COLUMN]
    values = [header]
    with pytest.raises(worker.DependencyNotReady, match="aguarda"):
        worker.resolve_photo_parent_row(conn, header, values, 707, "PAT-07", "Unidade A")
    assert "FROM public.patrimonios_sheets_outbox" in conn.fake_cursor.query
    assert conn.fake_cursor.params == (707,)


def test_missing_parent_row_requires_reconciliation_when_inventory_outbox_is_terminal():
    class FakeCursor:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, _query, _params):
            pass
        def fetchone(self):
            return ("synced",)

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    header = ["Nº de Patrimônio", worker.ID_COLUMN]
    with pytest.raises(worker.InventoryRowNotFound, match="reconciliação controlada"):
        worker.resolve_photo_parent_row(
            FakeConnection(), header, [header], 808, "PAT-08", "Unidade A"
        )
