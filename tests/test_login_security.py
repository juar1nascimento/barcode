import ast
from pathlib import Path

import auth_supabase
import login


def test_password_policy_requires_strong_password():
    assert auth_supabase.senha_forte("Abc12345")[0] is False
    assert auth_supabase.senha_forte("Abcdefgh1234!")[0] is True


def test_email_validation_is_strict_enough_for_login():
    assert auth_supabase.validar_email("usuario@serra.es.gov.br") is True
    assert auth_supabase.validar_email("usuario-sem-dominio") is False


def test_session_timeout_is_enforced_in_login_flow():
    source = Path("login.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "renderizar_login"
    )
    function_source = ast.get_source_segment(source, function) or ""

    assert "SESSAO_INATIVA_SEGUNDOS" in function_source
    assert "_limpar_sessao_autenticacao()" in function_source
    assert "time.time() - ultimo" in function_source


def test_login_does_not_store_plaintext_password():
    source = Path("login.py").read_text(encoding="utf-8")
    assert "st.session_state[\"login_pass\"]" in source
    assert "hash_senha" not in source
    assert "registrar_novo_usuario" not in source
    assert "verificar_senha" not in source


def test_auth_module_uses_supabase_auth_for_credentials():
    source = Path("auth_supabase.py").read_text(encoding="utf-8")
    assert "sign_in_with_password" in source
    assert "reset_password_for_email" in source
    assert "update_user" in source
