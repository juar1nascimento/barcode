import pandas as pd

import movimentacao_inventario as mov


def test_excluir_patrimonio_exato_remove_somente_o_registro_escolhido(monkeypatch):
    dados = pd.DataFrame([
        {"Setor": "Farmacia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-001", "Código de Barras": "CB-001", "Fabricante": "HP", "Data Cadastro": "", "Origem": "", "Status": "Ativo"},
        {"Setor": "Farmácia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-002", "Código de Barras": "CB-002", "Fabricante": "Dell", "Data Cadastro": "", "Origem": "", "Status": "Ativo"},
        {"Setor": "Farmácia", "Tipo de Patrimônio": "Monitores", "Nº de Patrimônio": "MON-001", "Código de Barras": "CB-003", "Fabricante": "HP", "Data Cadastro": "", "Origem": "", "Status": "Ativo"},
        {"Setor": "Recepção", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-003", "Código de Barras": "CB-004", "Fabricante": "Lenovo", "Data Cadastro": "", "Origem": "", "Status": "Ativo"},
    ])
    salvos = {}
    monkeypatch.setattr(mov, "_carregar", lambda unidade: dados.copy())
    monkeypatch.setattr(mov, "salvar_no_excel", lambda df, unidade: salvos.setdefault("df", df.copy()) is not None)

    ok, _ = mov.excluir_patrimonio_exato("Farmacia", "CPU", "CPU-002", "UBS Teste")

    assert ok is True
    resultado = salvos["df"]
    assert len(resultado) == 3
    assert "CPU-002" not in resultado["Nº de Patrimônio"].tolist()
    assert "CPU-001" in resultado["Nº de Patrimônio"].tolist()
    assert "MON-001" in resultado["Nº de Patrimônio"].tolist()
    assert "CPU-003" in resultado["Nº de Patrimônio"].tolist()


def test_excluir_patrimonio_exato_nao_apaga_setor_diferente(monkeypatch):
    dados = pd.DataFrame([
        {"Setor": "Farmácia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-001", "Código de Barras": "CB-001", "Fabricante": "HP", "Data Cadastro": "", "Origem": "", "Status": "Ativo"},
        {"Setor": "Recepção", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "CPU-001", "Código de Barras": "CB-009", "Fabricante": "Dell", "Data Cadastro": "", "Origem": "", "Status": "Ativo"},
    ])
    salvos = {}
    monkeypatch.setattr(mov, "_carregar", lambda unidade: dados.copy())
    monkeypatch.setattr(mov, "salvar_no_excel", lambda df, unidade: salvos.setdefault("df", df.copy()) is not None)

    ok, _ = mov.excluir_patrimonio_exato("Farmácia", "CPU", "CPU-001", "UBS Teste")

    assert ok is True
    resultado = salvos["df"]
    assert len(resultado) == 1
    assert resultado.iloc[0]["Setor"] == "Recepção"
