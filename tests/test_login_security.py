from pathlib import Path


def test_local_login_does_not_delegate_passwords_to_supabase_auth():
    source = Path("login.py").read_text(encoding="utf-8")
    assert 'from auth_supabase import' not in source
    assert 'DB_FILE = "db_usuarios.json"' in source
    assert "hash_senha" in source
    assert "verificar_senha" in source
    assert "registrar_novo_usuario" in source
    assert "request_password_reset" not in source


def test_password_policy_requires_exactly_eight_alphanumeric_characters():
    source = Path("login.py").read_text(encoding="utf-8")
    assert "def validar_senha_alfanumerica_8" in source
    assert "if len(senha) != 8:" in source
    assert "if not senha.isalnum():" in source


def test_email_validation_is_present_for_local_login():
    source = Path("login.py").read_text(encoding="utf-8")
    assert "def validar_email" in source
    assert "email.strip()" in source


def test_session_timeout_is_enforced_in_login_flow():
    source = Path("login.py").read_text(encoding="utf-8")
    assert "SESSAO_INATIVA_SEGUNDOS" in source
    assert "_limpar_sessao_autenticacao()" in source
    assert "time.time() - ultimo" in source


def test_password_recovery_is_local_and_signed():
    source = Path("login.py").read_text(encoding="utf-8")
    assert 'acao not in {"aprovar", "recusar", "redefinir"}' in source
    assert "approval_token_digests" in source
    assert "_criar_token_aprovacao" in source
    assert "enviar_email" in source
    assert 'st.session_state.reset_autorizado = True' in source


def test_password_reset_token_is_consumed_before_reset_screen():
    source = Path("login.py").read_text(encoding="utf-8")
    marker = 'if acao == "redefinir":'
    start = source.index(marker)
    end = source.index('st.session_state.email_solicitante', start)
    block = source[start:end]
    assert 'pop("redefinir", None)' in block
    assert "salvar_usuarios(db)" in block


def test_auth_uses_local_cache_when_persistent_store_is_unavailable(monkeypatch):
    import login

    cache = {"usuario@example.com": {"senha": "hash", "aprovado": True}}
    monkeypatch.setattr(login, "_carregar_usuarios_persistentes", lambda: None)
    monkeypatch.setattr(login, "_carregar_usuarios_local", lambda: cache)

    assert login.carregar_usuarios() == cache


def test_auth_prefers_persistent_store_and_refreshes_local_cache(monkeypatch):
    import login

    persistent = {"usuario@example.com": {"senha": "hash", "aprovado": True}}
    refreshed = []
    monkeypatch.setattr(login, "_carregar_usuarios_persistentes", lambda: persistent)
    monkeypatch.setattr(login, "_salvar_usuarios_local", lambda db: refreshed.append(db))

    assert login.carregar_usuarios() == persistent
    assert refreshed == [persistent]


def test_fresh_container_bootstraps_only_configured_admin_when_persistence_is_empty(monkeypatch):
    import login

    saved_local = []
    saved_persistent = []
    monkeypatch.setattr(login, "_carregar_usuarios_persistentes", lambda: {})
    monkeypatch.setattr(login, "_carregar_usuarios_local", lambda: {})
    monkeypatch.setattr(login, "_salvar_usuarios_local", lambda db: saved_local.append(db))
    monkeypatch.setattr(login, "_salvar_usuarios_persistentes", lambda db: saved_persistent.append(db) or True)
    monkeypatch.setattr(login, "st", type("SecretsStub", (), {"secrets": {"email": {"admin_email": "admin@example.com", "admin_password_hash": "adminhash"}}})())

    assert login.carregar_usuarios() == {
        "admin@example.com": {"senha": "adminhash", "aprovado": True}
    }
    assert saved_persistent
    assert saved_local


def test_auth_database_timeout_is_bounded_to_avoid_long_login_stalls():
    import login

    assert 0 < login.AUTH_DB_CONNECT_TIMEOUT_SECONDS <= 5


def test_persistent_auth_connection_failure_degrades_to_contingency(monkeypatch):
    import login

    def fail_connect(*args, **kwargs):
        raise OSError("database unavailable")

    monkeypatch.setattr(login.psycopg, "connect", fail_connect)
    monkeypatch.setattr(login, "_auth_database_url", lambda: "postgresql://test.invalid/db")

    assert login._carregar_usuarios_persistentes() is None


def test_save_keeps_local_cache_when_persistent_store_fails(monkeypatch):
    import login

    cache = {"usuario@example.com": {"senha": "hash", "aprovado": True}}
    saved_local = []
    monkeypatch.setattr(login, "_salvar_usuarios_local", lambda db: saved_local.append(db))
    monkeypatch.setattr(login, "_salvar_usuarios_persistentes", lambda db: False)

    login.salvar_usuarios(cache)

    assert saved_local == [cache]


def test_recovery_after_database_restoration_replaces_stale_local_cache(monkeypatch):
    import login

    stale_local = {"revogado@example.com": {"senha": "old", "aprovado": False}}
    persistent = {"usuario@example.com": {"senha": "new", "aprovado": True}}
    refreshed = []
    monkeypatch.setattr(login, "_carregar_usuarios_persistentes", lambda: persistent)
    monkeypatch.setattr(login, "_salvar_usuarios_local", lambda db: refreshed.append(db))

    assert login.carregar_usuarios() == persistent
    assert refreshed == [persistent]
