import pytest
from unittest.mock import MagicMock

import postgresql_persistencia as db


def test_dividir_setor():
    assert db._dividir_setor("Sala 12 - Cardiologia") == ("Sala 12", "Cardiologia")
    assert db._dividir_setor("Recepção") == ("Recepção", "")


@pytest.mark.parametrize("tipo", ["ENTRADA", "SAIDA", "TRANSFERENCIA"])
def test_registrar_movimentacao_valida_tipo_sem_conexao(monkeypatch, tipo):
    monkeypatch.setattr(db, "conectar", lambda: None)
    ok, movement_id, message = db.registrar_movimentacao("PAT-001", tipo, "teste")
    assert ok is False
    assert movement_id is None
    assert "conectar" in message.lower()


def test_registrar_movimentacao_rejeita_tipo_invalido():
    ok, movement_id, message = db.registrar_movimentacao("PAT-001", "INVALIDO", "teste")
    assert ok is False
    assert movement_id is None
    assert "inválido" in message.lower()


def test_registrar_movimentacao_exige_patrimonio_e_usuario():
    ok, movement_id, message = db.registrar_movimentacao("", "ENTRADA", "")
    assert ok is False
    assert movement_id is None
    assert "obrigatórios" in message.lower()


def test_registrar_movimentacao_rejeita_destino_ausente(monkeypatch):
    monkeypatch.setattr(db, "conectar", lambda: MagicMock())
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (1, "PAT-001", 1, 1)
    monkeypatch.setattr(db, "conectar", lambda: conn)
    ok, movement_id, message = db.registrar_movimentacao(
        "PAT-001", "TRANSFERENCIA", "teste"
    )
    assert ok is False
    assert movement_id is None
    assert "destino" in message.lower()
