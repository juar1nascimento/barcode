import pandas as pd

import movimentacao_inventario as mi


def _df(rows):
    return pd.DataFrame(rows, columns=mi.COLUNAS_INVENTARIO)


def test_registrar_entrada_respeita_data_recebimento(monkeypatch):
    armazenado = {}

    monkeypatch.setattr(mi, "_carregar", lambda unidade: _df([]))
    monkeypatch.setattr(mi, "salvar_no_excel", lambda df, unidade: armazenado.setdefault(unidade, df.copy()) is not None)

    ok, mensagem = mi.registrar_entrada(
        "CB-001", "Monitor/Tela", "UBS Feu Rosa", "Farmacia",
        numero_patrimonio="PAT-001", fabricante="hp", data_recebimento=__import__("datetime").date(2026, 1, 15)
    )

    assert ok is True
    assert "sucesso" in mensagem
    row = armazenado["UBS Feu Rosa"].iloc[0]
    assert row["Setor"] == "Farmácia"
    assert row["Fabricante"] == "HP"
    assert row["Data Cadastro"].startswith("2026-01-15")


def _equipamento_origem():
    return _df([{
        "Setor": "Farmácia", "Tipo de Patrimônio": "CPU", "Nº de Patrimônio": "PAT-10",
        "Código de Barras": "CB-10", "Fabricante": "Dell", "Data Cadastro": "2026-01-01 00:00:00",
        "Origem": "Cadastro", "Status": "Ativo"
    }])


def test_registrar_transferencia_cria_destino_e_marca_origem(monkeypatch):
    origem = _equipamento_origem()
    destino = _df([])
    salvos = {}

    def carregar(unidade):
        return (origem.copy(), None) if unidade == "UBS A" else (destino.copy(), None)

    def salvar(df, unidade):
        salvos[unidade] = df.copy()
        return True

    monkeypatch.setattr(mi, "carregar_dados_excel", carregar)
    monkeypatch.setattr(mi, "salvar_no_excel", salvar)

    ok, mensagem = mi.registrar_saida("CB-10", "UBS A", "Transferência para outra Unidade", "UBS B", "Mudança de local")

    assert ok is True
    assert "UBS A" in mensagem and "UBS B" in mensagem
    assert salvos["UBS A"].iloc[0]["Status"] == "Transferido"
    assert "UBS B" in salvos
    assert salvos["UBS B"].iloc[0]["Status"] == "Ativo"
    assert salvos["UBS B"].iloc[0]["Código de Barras"] == "CB-10"
    assert "UBS A" in salvos["UBS B"].iloc[0]["Origem"]


def test_transferencia_nao_altera_origem_se_destino_falhar(monkeypatch):
    origem = _equipamento_origem()
    destino = _df([])
    chamadas = []

    monkeypatch.setattr(mi, "carregar_dados_excel", lambda unidade: (origem.copy(), None) if unidade == "UBS A" else (destino.copy(), None))

    def salvar(df, unidade):
        chamadas.append(unidade)
        return False if unidade == "UBS B" else True

    monkeypatch.setattr(mi, "salvar_no_excel", salvar)

    ok, mensagem = mi.registrar_saida("CB-10", "UBS A", "Transferência para outra Unidade", "UBS B")

    assert ok is False
    assert "destino" in mensagem.lower()
    assert chamadas == ["UBS B"]


def test_transferencia_faz_rollback_se_origem_falhar(monkeypatch):
    origem = _equipamento_origem()
    destino = _df([])
    salvos = []

    monkeypatch.setattr(mi, "carregar_dados_excel", lambda unidade: (origem.copy(), None) if unidade == "UBS A" else (destino.copy(), None))

    def salvar(df, unidade):
        salvos.append((unidade, df.copy()))
        if unidade == "UBS A":
            return False
        return True

    monkeypatch.setattr(mi, "salvar_no_excel", salvar)

    ok, mensagem = mi.registrar_saida("CB-10", "UBS A", "Transferência para outra Unidade", "UBS B")

    assert ok is False
    assert "revertida" in mensagem.lower()
    assert [unidade for unidade, _ in salvos] == ["UBS B", "UBS A", "UBS B"]
    assert salvos[-1][1].empty


def test_registrar_saida_baixa_preserva_registro_com_status(monkeypatch):
    origem = _equipamento_origem()
    salvos = {}

    monkeypatch.setattr(mi, "carregar_dados_excel", lambda unidade: (origem.copy(), None))
    monkeypatch.setattr(mi, "salvar_no_excel", lambda df, unidade: salvos.setdefault(unidade, df.copy()) is not None)

    ok, mensagem = mi.registrar_saida("PAT-10", "UBS A", "Recolhimento / Desfazimento (Baixa)", observacoes="Equipamento inservível")

    assert ok is True
    assert salvos["UBS A"].iloc[0]["Status"] == "Baixado"
    assert "inservível" in salvos["UBS A"].iloc[0]["Origem"]
