import postgresql_persistencia as backend


def test_movimentacao_destrutiva_exige_admin(monkeypatch):
    monkeypatch.setattr(backend.st, "secrets", {"email": {"admin_email": "admin@serra.local"}})
    assert backend._usuario_pode_movimentar("SAIDA", "operador@serra.local") is False
    assert backend._usuario_pode_movimentar("TRANSFERENCIA", "operador@serra.local") is False


def test_movimentacao_destrutiva_permite_admin(monkeypatch):
    monkeypatch.setattr(backend.st, "secrets", {"email": {"admin_email": "Admin@Serra.local"}})
    assert backend._usuario_pode_movimentar("SAIDA", "admin@serra.local") is True
    assert backend._usuario_pode_movimentar("TRANSFERENCIA", " ADMIN@SERRA.LOCAL ") is True


def test_entrada_nao_exige_admin():
    assert backend._usuario_pode_movimentar("ENTRADA", "operador@serra.local") is True


def test_tipo_desconhecido_nao_elevado_a_operacao_destrutiva():
    assert backend._usuario_pode_movimentar("OUTRO", "operador@serra.local") is True
