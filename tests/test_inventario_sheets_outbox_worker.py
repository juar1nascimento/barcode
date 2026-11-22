from datetime import date
from types import SimpleNamespace

import pytest

import inventario_sheets_outbox_worker as worker


class ApiError(Exception):
    def __init__(self, status_code: int, headers=None):
        super().__init__(f"HTTP {status_code}")
        self.response = SimpleNamespace(
            status_code=status_code,
            headers=headers or {},
        )


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args):
        pass

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row

    def cursor(self):
        return FakeCursor(self.row)


class FakeWorksheet:
    id = 7

    def __init__(self, values):
        self.values = values
        self.batch_calls = []

    def get_all_values(self):
        return self.values

    def batch_update(self, updates, value_input_option):
        self.batch_calls.append((updates, value_input_option))
        for update in updates:
            column = update["range"].split("2", 1)[0]
            index = 0
            for char in column:
                index = index * 26 + ord(char.upper()) - 64
            self.values[1][index - 1] = update["values"][0][0]

    def get(self, _range):
        return [self.values[1]]


class FakeSpreadsheet:
    def __init__(self, worksheet):
        self._worksheet = worksheet

    def worksheet(self, _name):
        return self._worksheet


def _patrimonio_row(numero="PAT-001"):
    return (
        42,
        numero,
        "BAR-42",
        "Notebook",
        "Dell",
        date(2026, 1, 15),
        "Unidade Central",
        "Administrativo",
    )


def _sheet():
    return FakeWorksheet([
        [
            "Setor",
            "Tipo de Patrimônio",
            "Nº de Patrimônio",
            "Fabricante",
            "Data Cadastro",
            "Código de Barras",
            "Origem",
        ],
        ["Antigo", "Antigo", "PAT-001", "Antigo", "2020-01-01", "", "preservar"],
    ])


def test_sheets_call_retries_quota_error_with_jitter(monkeypatch):
    calls = {"count": 0}
    sleeps = []
    monkeypatch.setattr(worker.time, "sleep", sleeps.append)
    monkeypatch.setattr(worker.secrets, "randbelow", lambda _limit: 250)

    def callback():
        calls["count"] += 1
        if calls["count"] == 1:
            raise ApiError(429, {"Retry-After": "3"})
        return "ok"

    assert worker._sheets_call("test", callback, attempts=3) == "ok"
    assert calls["count"] == 2
    assert sleeps == [3]


def test_sync_one_batches_existing_row_and_preserves_other_columns():
    worksheet = _sheet()
    worker.sync_one(
        FakeConnection(_patrimonio_row()),
        FakeSpreadsheet(worksheet),
        42,
    )

    assert len(worksheet.batch_calls) == 1
    updates, value_input_option = worksheet.batch_calls[0]
    assert value_input_option == "RAW"
    assert len(updates) == 6
    assert worksheet.values[1][0] == "Administrativo"
    assert worksheet.values[1][1] == "Notebook"
    assert worksheet.values[1][2] == "PAT-001"
    assert worksheet.values[1][3] == "Dell"
    assert worksheet.values[1][4] == "2026-01-15"
    assert worksheet.values[1][5] == "BAR-42"
    assert worksheet.values[1][6] == "preservar"


def test_sync_one_refuses_duplicate_patrimony_rows_without_writing():
    worksheet = _sheet()
    worksheet.values.append(list(worksheet.values[1]))

    with pytest.raises(RuntimeError, match="contém 2 linhas"):
        worker.sync_one(
            FakeConnection(_patrimonio_row()),
            FakeSpreadsheet(worksheet),
            42,
        )

    assert worksheet.batch_calls == []


def test_sync_one_refuses_blank_patrimony_number():
    worksheet = _sheet()

    with pytest.raises(RuntimeError, match="sem número patrimonial"):
        worker.sync_one(
            FakeConnection(_patrimonio_row("")),
            FakeSpreadsheet(worksheet),
            42,
        )

    assert worksheet.batch_calls == []
