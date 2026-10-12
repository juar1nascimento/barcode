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
