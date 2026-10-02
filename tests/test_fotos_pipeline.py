import os

import sheets_outbox_worker as worker


def test_col_letter():
    assert worker.col_letter(1) == "A"
    assert worker.col_letter(26) == "Z"
    assert worker.col_letter(27) == "AA"
    assert worker.col_letter(36) == "AJ"


def test_sheet_url_canonical_path(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co/")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    class Response:
        ok = True
        def json(self):
            return {"signedURL": "/storage/v1/object/sign/patrimonio-fotos/abc?token=test"}
    monkeypatch.setattr(worker.requests, "post", lambda *args, **kwargs: Response())
    assert worker.sheet_url("2/foto-001-a b.jpg").startswith(
        "https://example.supabase.co/storage/v1/object/sign/"
    )


def test_sheet_url_removes_leading_slash(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    class Response:
        ok = True
        def json(self):
            return {"signedURL": "/storage/v1/object/sign/patrimonio-fotos/abc?token=test"}
    monkeypatch.setattr(worker.requests, "post", lambda *args, **kwargs: Response())
    assert worker.sheet_url("/2/foto-002.jpg").endswith("?token=test")


def test_signed_storage_url_preserves_storage_api_base(monkeypatch):
    import supabase_storage as storage

    monkeypatch.setattr(
        storage,
        "_config_supabase",
        lambda: {"url": "https://example.supabase.co", "key": "test-key"},
    )

    class Response:
        ok = True

        def json(self):
            return {
                "signedURL": "/object/sign/patrimonio-fotos/2/foto-001.jpg?token=test"
            }

    monkeypatch.setattr(storage.requests, "post", lambda *args, **kwargs: Response())

    url = storage.criar_url_assinada_storage(
        "patrimonio-fotos", "2/foto-001.jpg", expires_in=3600
    )
    assert url == (
        "https://example.supabase.co/storage/v1/"
        "object/sign/patrimonio-fotos/2/foto-001.jpg?token=test"
    )


def test_required_env_rejects_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    try:
        worker.env("SUPABASE_URL")
    except RuntimeError as exc:
        assert "SUPABASE_URL" in str(exc)
    else:
        raise AssertionError("env() deveria rejeitar variável ausente")


def test_fotos_table_uses_periodic_fragment_refresh():
    import sistema_inventario as app

    assert app.FOTO_URL_EXPIRATION_SECONDS == 86_400
    assert app.FOTO_URL_REFRESH_INTERVAL == "50m"
    assert getattr(app._renderizar_tabela_site, "__name__", "") == "_renderizar_tabela_site"
    assert getattr(app._renderizar_tabela_site_fragment, "__name__", "") == "_renderizar_tabela_site_fragment"


def test_signed_url_expiry_and_path_helpers(monkeypatch):
    import base64
    import json
    import sheets_outbox_worker as worker

    payload = {"exp": 2_000_000_000}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    token = f"header.{encoded}.signature"
    url = (
        "https://example.supabase.co/storage/v1/object/sign/"
        "patrimonio-fotos/2/foto-001.jpg?token=" + token
    )
    assert worker._signed_url_expiry(url) == 2_000_000_000
    assert worker._photo_path_from_url(url) == "2/foto-001.jpg"


def test_photo_formula_is_image_and_hyperlink():
    import sheets_outbox_worker as worker

    formula = worker._photo_formula(
        "https://example.supabase.co/storage/v1/object/sign/"
        "patrimonio-fotos/2/foto.jpg?token=test"
    )
    assert formula.startswith('=HYPERLINK("')
    assert 'IMAGE("' in formula
    assert ',4,96,96))' in formula


def test_sheet_url_uses_24_hour_expiration(monkeypatch):
    import sheets_outbox_worker as worker

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    captured = {}

    class Response:
        ok = True
        def json(self):
            return {"signedURL": "/storage/v1/object/sign/patrimonio-fotos/2/foto.jpg?token=test"}

    def fake_post(*args, **kwargs):
        captured["json"] = kwargs["json"]
        return Response()

    monkeypatch.setattr(worker.requests, "post", fake_post)
    worker.sheet_url("2/foto.jpg")
    assert captured["json"]["expiresIn"] == 86_400
