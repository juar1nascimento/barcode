"""Regression tests for failed-event recovery in the alternate Sheets outbox consumer."""

import sincronizador_google_sheets as sincronizador


class _SQLFragment:
    def __init__(self, value):
        self.value = value

    def format(self, **kwargs):
        values = {
            key: item.value if isinstance(item, _SQLFragment) else str(item)
            for key, item in kwargs.items()
        }
        return _SQLFragment(self.value.format(**values))


class _FakeSQL:
    @staticmethod
    def SQL(value):
        return _SQLFragment(value)

    @staticmethod
    def Identifier(value):
        return _SQLFragment(f'"{value}"')


class _FakeCursor:
    def __init__(self):
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        self.query = query.value
        self.params = params

    def fetchall(self):
        return []


class _FakeConnection:
    def __init__(self):
        self.fake_cursor = _FakeCursor()
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        raise AssertionError("rollback não deveria ser chamado")

    def close(self):
        self.closed = True


def test_claim_retries_failed_events_only_after_backoff_and_before_attempt_limit(monkeypatch):
    conn = _FakeConnection()
    monkeypatch.setattr(sincronizador, "conectar", lambda: conn)
    monkeypatch.setattr(sincronizador, "sql", _FakeSQL)

    assert sincronizador._claim("patrimonios_sheets_outbox", 10) == []

    query = " ".join(conn.fake_cursor.query.split())
    assert "status IN ('pending', 'failed')" in query
    assert "proxima_tentativa_em <= now()" in query
    assert "tentativas < %s" in query
    assert "status='processing'" in query
    assert "tentativas < %s" in query
    assert "tentativas >= %s" in query
    assert "status='dead_letter'" in query
    assert "FOR UPDATE SKIP LOCKED" in query
    assert conn.fake_cursor.params == (
        sincronizador.STALE_MINUTES,
        sincronizador.MAX_TENTATIVAS,
        sincronizador.MAX_TENTATIVAS,
        sincronizador.STALE_MINUTES,
        sincronizador.MAX_TENTATIVAS,
        10,
    )
    assert conn.commits == 1
    assert conn.closed


def test_claim_rejects_unknown_outbox_table_before_connecting(monkeypatch):
    connected = []
    monkeypatch.setattr(sincronizador, "conectar", lambda: connected.append(True))

    try:
        sincronizador._claim("unexpected_table", 10)
    except ValueError as exc:
        assert "Tabela de outbox inválida" in str(exc)
    else:
        raise AssertionError("Tabela inválida deveria ser recusada")

    assert connected == []
