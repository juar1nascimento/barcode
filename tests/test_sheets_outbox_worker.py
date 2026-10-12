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
