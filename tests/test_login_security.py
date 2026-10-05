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
