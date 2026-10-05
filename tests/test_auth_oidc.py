from pathlib import Path


def test_keycloak_login_uses_original_portal_structure():
    source = Path("auth_oidc.py").read_text(encoding="utf-8")
    required = (
        'st.form("glpi_login_form", clear_on_submit=False)',
        'Faça login na sua conta',
        'st.text_input("Usuário"',
        'st.text_input("Senha"',
        'SERRA.LOCAL',
        'st.form_submit_button("Entrar"',
        'iniciar_login_oidc()',
    )
    for marker in required:
        assert marker in source


def test_keycloak_portal_does_not_accept_or_validate_local_passwords():
    source = Path("auth_oidc.py").read_text(encoding="utf-8")
    start = source.index("def renderizar_login_oidc")
    block = source[start:]
    assert "verificar_senha(" not in block
    assert "carregar_usuarios(" not in block
    assert 'disabled=True' in block


def test_keycloak_oidc_requires_stable_subject_and_explicit_admin_role():
    source = Path("auth_oidc.py").read_text(encoding="utf-8")
    assert 'subject = str(_claim("sub", "") or "").strip()' in source
    assert '"is_admin": "admin" in roles' in source
    assert 'admin" in roles' in source
