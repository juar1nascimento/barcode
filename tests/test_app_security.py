import ast
from pathlib import Path


def _load_app_source() -> str:
    return Path("app.py").read_text(encoding="utf-8")


def test_native_streamlit_menu_is_hidden_for_application_users():
    source = _load_app_source()
    assert "#MainMenu { visibility: hidden !important; }" in source
    assert 'header [data-testid="stToolbar"] { visibility: hidden !important; }' in source


def test_administrative_pages_are_guarded_by_admin_check():
    source = _load_app_source()
    tree = ast.parse(source)

    administrative_pages = {
        "auditoria_pre_migracao",
        "preflight_supabase",
        "saude_integracao",
        "teste_upload_foto",
    }
    guarded = set()

    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        text = ast.get_source_segment(source, node) or ""
        if "st.session_state.pagina_atual ==" not in text:
            continue
        for page in administrative_pages:
            if f'pagina_atual == "{page}"' in text:
                guarded.add(page)
                assert "if not is_admin:" in text
                assert "Acesso não autorizado." in text

    assert guarded == administrative_pages
