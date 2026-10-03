import postgresql_persistencia as persistence


def test_sector_whitespace_is_normalized_before_persistence(monkeypatch):
    class DummyConn:
        def cursor(self):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, *args):
            return None
        def fetchone(self):
            return (1,)
        def commit(self):
            pass
        def rollback(self):
            pass
        def close(self):
            pass

    captured = {}

    def fake_garantir_unidade(cur, unidade):
        return 10

    def fake_garantir_setor(cur, unidade_id, setor):
        captured["setor"] = setor
        return 20

    monkeypatch.setattr(persistence, "conectar", lambda: DummyConn())
    monkeypatch.setattr(persistence, "garantir_unidade", fake_garantir_unidade)
    monkeypatch.setattr(persistence, "garantir_setor", fake_garantir_setor)

    ok, ids, _ = persistence.salvar_patrimonios_em_lote([{
        "codigo_barras": "TESTE-CODIGO",
        "numero_patrimonio": "TESTE-CODIGO",
        "tipo": "Mouse",
        "setor": "Sala   de   Preparo",
        "unidade": "UBS Feu Rosa",
    }])

    assert ok is True
    assert ids == [1]
    assert captured["setor"] == "Sala de Preparo"
