import pandas as pd


def test_migracao_dry_run_nao_cria_unidade_ou_setor(monkeypatch):
    import migrar_google_para_postgresql as mig

    df = pd.DataFrame([{
        "Setor": "Farmacia",
        "Tipo de Patrimônio": "CPU",
        "Nº de Patrimônio": "DRY-001",
        "Fabricante": "Dell",
        "Data Cadastro": "",
        "Foto": "",
    }])

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params=()):
            self.sql = sql
            self.params = params
        def fetchone(self):
            if "FROM unidades" in self.sql:
                return None
            if "FROM patrimonios" in self.sql:
                return None
            return None

    class Conn:
        def cursor(self): return Cursor()
        def rollback(self): pass
        def commit(self): raise AssertionError("dry-run não deve fazer commit")
        def close(self): pass

    monkeypatch.setattr(mig, "conectar", lambda: Conn())
    monkeypatch.setattr(
        mig,
        "garantir_unidade",
        lambda *args: (_ for _ in ()).throw(AssertionError("garantir_unidade não deve ser chamado no dry-run")),
    )
    monkeypatch.setattr(
        mig,
        "garantir_setor",
        lambda *args: (_ for _ in ()).throw(AssertionError("garantir_setor não deve ser chamado no dry-run")),
    )

    resultado = mig.migrar_unidade(
        "Almoxarifado Central SESA",
        dry_run=True,
        dados_lote={
            "Almoxarifado Central SESA": (df, "Google Sheets (Almoxarifado Central SESA)")
        },
    )

    assert resultado["simulacao"] is True
    assert resultado["candidatos"] == 1
    assert resultado["inseridos"] == 1
    assert resultado["erros"] == []
