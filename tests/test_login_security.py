import ast
from pathlib import Path

import login


def test_existing_account_cannot_be_overwritten():
    existing = {
        "admin@example.com": {
            "senha": login.hash_senha("Abc12345"),
            "aprovado": True,
        }
    }
    original_hash = existing["admin@example.com"]["senha"]

    assert login.registrar_novo_usuario(existing, "admin@example.com", "Xyz98765") is False
    assert existing["admin@example.com"]["senha"] == original_hash
    assert existing["admin@example.com"]["aprovado"] is True


def test_new_account_is_created_pending_approval():
    users = {}

    assert login.registrar_novo_usuario(users, "novo@example.com", "Abc12345") is True
    assert users["novo@example.com"]["aprovado"] is False

    valido, migrar = login.verificar_senha("Abc12345", users["novo@example.com"]["senha"])
    assert valido is True
    assert migrar is False


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
    assert "time.time() - ultimo_acesso" in function_source
