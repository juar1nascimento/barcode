import pandas as pd


def test_auditoria_reconciliacao_identifica_divergencia_por_numero(monkeypatch):
    import auditoria_reconciliacao_postgresql as audit

    sheets = pd.DataFrame([{
        "Setor": "Farmacia",
        "Tipo de Patrimônio": "CPU",
        "Nº de Patrimônio": "PAT-001",
        "Fabricante": "Dell",
        "Data Cadastro": "",
        "Foto": "",
    }])
    pg = pd.DataFrame([{
        "id": 1,
        "unidade": "UBS Teste",
        "setor": "Recepção",
        "numero_consultorio": None,
        "especialidade": None,
        "tipo": "CPU",
        "numero_patrimonio": "PAT-001",
        "codigo_barras": None,
        "fabricante": "Dell",
        "data_cadastro": None,
        "atualizado_em": None,
        "possui_foto": False,
    }])
    monkeypatch.setattr(audit, "_carregar_postgresql", lambda unidade: pg)

    resultado = audit.auditar_unidade(
        "UBS Teste",
        {"UBS Teste": (sheets, "Google Sheets (UBS Teste)")},
    )

    assert resultado["sheets_total"] == 1
    assert resultado["postgresql_total"] == 1
    assert resultado["somente_sheets"] == 0
    assert resultado["somente_postgresql"] == 0
    assert resultado["divergencias"] == 1
    assert resultado["detalhes_divergencias"][0]["campo"] == "setor"


def test_auditoria_reconciliacao_identifica_foto_no_postgresql(monkeypatch):
    import auditoria_reconciliacao_postgresql as audit

    sheets = pd.DataFrame([{
        "Setor": "Farmacia",
        "Tipo de Patrimônio": "CPU",
        "Nº de Patrimônio": "PAT-002",
        "Fabricante": "Dell",
        "Data Cadastro": "",
        "Foto": "",
    }])
    pg = pd.DataFrame([{
        "id": 2,
        "unidade": "Almoxarifado Central SESA",
        "setor": "Farmacia",
        "numero_consultorio": None,
        "especialidade": None,
        "tipo": "CPU",
        "numero_patrimonio": "PAT-002",
        "codigo_barras": None,
        "fabricante": "Dell",
        "data_cadastro": None,
        "atualizado_em": None,
        "possui_foto": True,
    }])
    monkeypatch.setattr(audit, "_carregar_postgresql", lambda unidade: pg)

    resultado = audit.auditar_unidade(
        "Almoxarifado Central SESA",
        {"Almoxarifado Central SESA": (sheets, "Google Sheets (Almoxarifado Central SESA)")},
    )

    assert resultado["iguais"] == 1
    assert resultado["fotos_postgresql"] == 1
