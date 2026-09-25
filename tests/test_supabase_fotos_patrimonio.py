from __future__ import annotations

import supabase_fotos_patrimonio as fotos


def test_usuario_app_nao_autorizado_sem_sessao(monkeypatch):
    monkeypatch.setattr(fotos.st, "session_state", {})
    assert fotos.usuario_app_autorizado() is False


def test_usuario_app_autorizado_com_login_proprio(monkeypatch):
    monkeypatch.setattr(
        fotos.st,
        "session_state",
        {"autenticado": True, "usuario_logado": "teste"},
    )
    assert fotos.usuario_app_autorizado() is True


def test_usuario_app_nao_autorizado_sem_usuario(monkeypatch):
    monkeypatch.setattr(
        fotos.st,
        "session_state",
        {"autenticado": True, "usuario_logado": ""},
    )
    assert fotos.usuario_app_autorizado() is False
