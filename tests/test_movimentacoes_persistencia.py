import pandas as pd
import pytest

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import postgresql_persistencia as backend


class _Cursor:
    def __init__(self):
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return False


class _Conn:
    def __init__(self):
        self.cursor_obj = _Cursor()
    def cursor(self): return self.cursor_obj
    def rollback(self): pass
    def commit(self): raise AssertionError("não deve chegar ao banco")
    def close(self): pass


@pytest.mark.parametrize("tipo", ["SAIDA", "TRANSFERENCIA"])
def test_movimentacao_restrita_a_admin_antes_de_abrir_conexao(monkeypatch, tipo):
    backend.st.session_state.clear()
    backend.st.session_state["usuario_logado"] = "operador@ses a.local".replace(" ", "")
    monkeypatch.setitem(backend.st.secrets, "email", {"admin_email": "admin@serra.local"})
    monkeypatch.setattr(backend, "conectar", lambda: (_ for _ in ()).throw(AssertionError("não deve conectar")))

    ok, movimento_id, mensagem = backend.registrar_movimentacao(
        codigo_patrimonio="PAT-001",
        tipo=tipo,
        usuario="operador@serra.local",
    )

    assert ok is False
    assert movimento_id is None
    assert "não autorizada" in mensagem.lower()


def test_entrada_deve_chegar_ao_backend_para_usuario_autenticado(monkeypatch):
    backend.st.session_state.clear()
    backend.st.session_state["usuario_logado"] = "operador@serra.local"
    monkeypatch.setitem(backend.st.secrets, "email", {"admin_email": "admin@serra.local"})

    class Cursor:
        def __init__(self):
            self.step = 0
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def execute(self, query, params=None):
            self.step += 1
        def fetchone(self):
            if self.step == 1:
                return (10, "PAT-001", 1, 2)
            if self.step == 2:
                return (1,)
            if self.step == 3:
                return (99,)
            return None
        @property
        def rowcount(self): return 1

    class Conn:
        def cursor(self): return Cursor()
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass

    monkeypatch.setattr(backend, "conectar", lambda: Conn())
    ok, movimento_id, mensagem = backend.registrar_movimentacao(
        codigo_patrimonio="PAT-001", tipo="ENTRADA",
        usuario="operador@serra.local", unidade_destino_id=1, setor_destino_id=2,
        motivo="Recebimento"
    )
    assert ok is True
    assert movimento_id == 99
    assert "sucesso" in mensagem.lower()
