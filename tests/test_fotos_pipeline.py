import os

import sheets_outbox_worker as worker


def test_col_letter():
    assert worker.col_letter(1) == "A"
    assert worker.col_letter(26) == "Z"
    assert worker.col_letter(27) == "AA"
    assert worker.col_letter(36) == "AJ"


def test_sheet_url_canonical_path(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co/")
    assert worker.sheet_url("2/foto-001-a b.jpg") == (
        "https://example.supabase.co/storage/v1/object/public/"
        "patrimonio-fotos/2/foto-001-a%20b.jpg"
    )


def test_sheet_url_removes_leading_slash(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    assert worker.sheet_url("/2/foto-002.jpg").endswith(
        "/storage/v1/object/public/patrimonio-fotos/2/foto-002.jpg"
    )


def test_required_env_rejects_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    try:
        worker.env("SUPABASE_URL")
    except RuntimeError as exc:
        assert "SUPABASE_URL" in str(exc)
    else:
        raise AssertionError("env() deveria rejeitar variável ausente")
