from pathlib import Path


def test_logout_uses_central_session_cleanup():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "from login import renderizar_login, _limpar_sessao_autenticacao" in source
    assert "_limpar_sessao_autenticacao()" in source
    assert 'st.session_state.usuario_logado = ""' not in source


def test_photo_modal_does_not_navigate_to_signed_url():
    source = Path("sistema_inventario.py").read_text(encoding="utf-8")
    assert 'class="foto-link"' in source
    assert 'data-foto-url=' in source
    assert "event.preventDefault()" in source
    assert "window.location" not in source
    assert "href=" not in source


def test_photo_errors_do_not_redirect_to_login():
    source = Path("fotos_patrimonio.py").read_text(encoding="utf-8")
    assert "st.warning(" in source
    assert "st.rerun()" not in source
    assert "st.query_params" not in source
