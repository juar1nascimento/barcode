import pytest
from unittest.mock import MagicMock

import postgresql_persistencia as db


@pytest.fixture(autouse=True)
def _admin_de_teste(monkeypatch):
    monkeypatch.setattr(db.st, "secrets", {"email": {"admin_email": "operador"}})



def test_dividir_setor():
    assert db._dividir_setor("Sala 12 - Cardiologia") == ("Sala 12 - Cardiologia", None, None)
    assert db._dividir_setor("Recepção") == ("Recepção", None, None)


@pytest.mark.parametrize("tipo", ["ENTRADA", "SAIDA", "TRANSFERENCIA"])
def test_registrar_movimentacao_valida_tipo_sem_conexao(monkeypatch, tipo):
    monkeypatch.setattr(db, "conectar", lambda: None)
    ok, movement_id, message = db.registrar_movimentacao("PAT-001", tipo, "teste")
    assert ok is False
    assert movement_id is None
    assert "conectar" in message.lower()


def test_buscar_patrimonio_por_codigo_prioriza_numero(monkeypatch):
    cur = MagicMock()
    cur.fetchone.side_effect = [
        (10, "PAT-001", 1, 2),
    ]

    row = db._buscar_patrimonio_por_codigo(cur, "PAT-001")

    assert row == (10, "PAT-001", 1, 2)
    assert cur.execute.call_count == 1
    assert "numero_patrimonio" in cur.execute.call_args.args[0]
    assert cur.execute.call_args.args[1] == ("PAT-001",)


def test_buscar_patrimonio_por_codigo_faz_fallback_para_barcode(monkeypatch):
    cur = MagicMock()
    cur.fetchone.side_effect = [
        None,
        (11, "PAT-002", 1, 3),
    ]

    row = db._buscar_patrimonio_por_codigo(cur, "BAR-002")

    assert row == (11, "PAT-002", 1, 3)
    assert cur.execute.call_count == 2
    assert "numero_patrimonio" in cur.execute.call_args_list[0].args[0]
    assert "codigo_barras" in cur.execute.call_args_list[1].args[0]


def test_buscar_patrimonio_por_codigo_preserva_prioridade_do_numero_sobre_barcode():
    cur = MagicMock()
    cur.fetchone.side_effect = [
        (20, "CODIGO-COMUM", 1, 2),
    ]

    row = db._buscar_patrimonio_por_codigo(cur, "CODIGO-COMUM")

    assert row[0] == 20
    assert cur.execute.call_count == 1


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



def _conexao_movimentacao(monkeypatch, fetchone_side_effect):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = fetchone_side_effect
    monkeypatch.setattr(db, "conectar", lambda: conn)
    return conn, cur


def test_registrar_movimentacao_entrada_valida(monkeypatch):
    conn, cur = _conexao_movimentacao(
        monkeypatch,
        [
            (10, "PAT-001", 1, 2),
            (1,),
            (100,),
        ],
    )

    ok, movement_id, message = db.registrar_movimentacao(
        "PAT-001", "ENTRADA", "operador", 3, 4, "recebimento", "teste"
    )

    assert ok is True
    assert movement_id == 100
    assert "ENTRADA" in message
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()
    assert any("movimentacoes_patrimonio" in str(call.args[0]) for call in cur.execute.call_args_list)


def test_registrar_movimentacao_saida_valida(monkeypatch):
    conn, cur = _conexao_movimentacao(
        monkeypatch,
        [
            (10, "PAT-001", 1, 2),
            (101,),
        ],
    )

    ok, movement_id, message = db.registrar_movimentacao(
        "PAT-001", "SAIDA", "operador", motivo="baixa"
    )

    assert ok is True
    assert movement_id == 101
    assert "SAIDA" in message
    conn.commit.assert_called_once()
    assert not any("SET unidade_id" in str(call.args[0]) for call in cur.execute.call_args_list)


def test_registrar_movimentacao_transferencia_valida(monkeypatch):
    conn, cur = _conexao_movimentacao(
        monkeypatch,
        [
            (10, "PAT-001", 1, 2),
            (1,),
            (102,),
        ],
    )

    ok, movement_id, message = db.registrar_movimentacao(
        "PAT-001", "TRANSFERENCIA", "operador", 3, 4
    )

    assert ok is True
    assert movement_id == 102
    assert "TRANSFERENCIA" in message
    conn.commit.assert_called_once()
    assert any("SET unidade_id" in str(call.args[0]) for call in cur.execute.call_args_list)


def test_registrar_movimentacao_rejeita_setor_de_destino_de_outra_unidade(monkeypatch):
    conn, cur = _conexao_movimentacao(
        monkeypatch,
        [
            (10, "PAT-001", 1, 2),
            None,
        ],
    )

    ok, movement_id, message = db.registrar_movimentacao(
        "PAT-001", "TRANSFERENCIA", "operador", 3, 99
    )

    assert ok is False
    assert movement_id is None
    assert "não pertence à unidade" in message
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    assert not any("INSERT INTO movimentacoes_patrimonio" in str(call.args[0]) for call in cur.execute.call_args_list)


def test_registrar_movimentacao_faz_rollback_se_banco_rejeitar_integridade(monkeypatch):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [(10, "PAT-001", 1, 2), (1,)]
    cur.execute.side_effect = [None, None, RuntimeError("origem do patrimônio não corresponde")]
    monkeypatch.setattr(db, "conectar", lambda: conn)

    ok, movement_id, message = db.registrar_movimentacao(
        "PAT-001", "TRANSFERENCIA", "operador", 3, 4
    )

    assert ok is False
    assert movement_id is None
    assert "falha ao registrar movimentação" in message.lower()
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()

def test_registrar_movimentacao_rejeita_setor_destino_inativo(monkeypatch):
    conn, cur = _conexao_movimentacao(
        monkeypatch,
        [
            (10, "PAT-001", 1, 2),
            None,
        ],
    )

    ok, movement_id, message = db.registrar_movimentacao(
        "PAT-001", "TRANSFERENCIA", "operador", 3, 99
    )

    assert ok is False
    assert movement_id is None
    assert "não pertence à unidade" in message
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    assert not any(
        "INSERT INTO movimentacoes_patrimonio" in str(call.args[0])
        for call in cur.execute.call_args_list
    )


def test_registrar_movimentacao_rejeita_transferencia_para_mesma_localizacao(monkeypatch):
    conn, cur = _conexao_movimentacao(
        monkeypatch,
        [
            (10, "PAT-001", 3, 4),
            (1,),
        ],
    )

    ok, movement_id, message = db.registrar_movimentacao(
        "PAT-001", "TRANSFERENCIA", "operador", 3, 4
    )

    assert ok is False
    assert movement_id is None
    assert "já está na localização" in message.lower()
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    assert not any(
        "INSERT INTO movimentacoes_patrimonio" in str(call.args[0])
        for call in cur.execute.call_args_list
    )
