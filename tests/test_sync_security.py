import inventario_sheets_outbox_worker as inventory_worker
import fotos_patrimonio


def test_safe_error_redacts_database_credentials():
    value = inventory_worker.safe_error(
        "connection failed: postgresql://user:senha-secreta@db.example.com:5432/inventario"
    )
    assert "senha-secreta" not in value
    assert "user:senha-secreta" not in value
    assert "postgresql://[REDACTED]" in value


def test_safe_error_redacts_bearer_and_token():
    value = inventory_worker.safe_error(
        "authorization Bearer abc123.secret-token token=super-secret"
    )
    assert "abc123.secret-token" not in value
    assert "super-secret" not in value
    assert "Bearer [REDACTED]" in value
    assert "token=[REDACTED]" in value


def test_safe_error_redacts_pem():
    value = inventory_worker.safe_error(
        "credential -----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"
    )
    assert "secret" not in value
    assert "[REDACTED PEM]" in value


def test_photo_sync_does_not_expose_internal_exception():
    source = open("fotos_patrimonio.py", encoding="utf-8").read()
    assert "Falha ao sincronizar as fotografias no Google Sheets." in source
    assert "Falha ao sincronizar fotos no Google Sheets: {exc}" not in source

# Cobertura de segurança da sincronização mantida como requisito de CI.
