from pathlib import Path

import auth_supabase


def test_password_policy_requires_strong_password():
    assert auth_supabase.senha_forte("Abc12345")[0] is False
    assert auth_supabase.senha_forte("Abcdefgh1234!")[0] is True


def test_email_validation_is_strict_enough_for_login():
    assert auth_supabase.validar_email("usuario@serra.es.gov.br") is True
    assert auth_supabase.validar_email("usuario-sem-dominio") is False


def test_login_flow_uses_supabase_auth():
    login_source = Path("login.py").read_text(encoding="utf-8")
    auth_source = Path("auth_supabase.py").read_text(encoding="utf-8")

    assert "sign_in(email, senha)" in login_source
    assert "sign_in_with_password" in auth_source
    assert 'st.session_state["login_pass"]' not in login_source
    assert "hash_senha" not in login_source
    assert "registrar_novo_usuario" not in login_source
    assert "verificar_senha" not in login_source


def test_session_timeout_is_enforced_in_login_flow():
    source = Path("login.py").read_text(encoding="utf-8")
    assert "SESSAO_INATIVA_SEGUNDOS" in source
    assert "_limpar_sessao_autenticacao()" in source
    assert "time.time() - ultimo" in source


def test_password_recovery_uses_supabase_auth():
    source = Path("login.py").read_text(encoding="utf-8")
    auth_source = Path("auth_supabase.py").read_text(encoding="utf-8")

    assert "request_password_reset(email.strip().lower(), _url_base())" in source
    assert "reset_password_for_email" in auth_source
    assert "update_user" in auth_source
