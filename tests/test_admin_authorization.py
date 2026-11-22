import pytest

from login import usuario_e_admin


@pytest.mark.parametrize(
    ("usuario", "admin_email", "expected"),
    [
        ("admin@serra.es.gov.br", "admin@serra.es.gov.br", True),
        (" Admin@Serra.ES.Gov.Br ", "admin@serra.es.gov.br", True),
        ("usuario@serra.es.gov.br", "admin@serra.es.gov.br", False),
        ("", "admin@serra.es.gov.br", False),
        ("admin@serra.es.gov.br", "", False),
        ("admin@serra.es.gov.br", None, False),
    ],
)
def test_admin_authorization_uses_one_normalized_identity(
    usuario, admin_email, expected, monkeypatch
):
    if admin_email is None:
        monkeypatch.setattr("login._email_config", lambda: {})
    assert usuario_e_admin(usuario, admin_email) is expected


def test_admin_authorization_reads_authenticated_session_and_config(monkeypatch):
    monkeypatch.setattr(
        "login.st.session_state",
        {"usuario_logado": " ADMIN@SERRA.ES.GOV.BR "},
    )
    monkeypatch.setattr(
        "login._email_config",
        lambda: {"admin_email": "admin@serra.es.gov.br"},
    )
    assert usuario_e_admin() is True


def test_admin_authorization_fails_closed_without_configured_admin(monkeypatch):
    monkeypatch.setattr(
        "login.st.session_state",
        {"usuario_logado": "admin@serra.es.gov.br"},
    )
    monkeypatch.setattr("login._email_config", lambda: {})
    assert usuario_e_admin() is False



def test_admin_authorization_fails_closed_without_authenticated_user(monkeypatch):
    monkeypatch.setattr("login.st.session_state", {})
    monkeypatch.setattr(
        "login._email_config",
        lambda: {"admin_email": "admin@serra.es.gov.br"},
    )
    assert usuario_e_admin() is False
