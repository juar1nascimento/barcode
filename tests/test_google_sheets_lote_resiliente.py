from __future__ import annotations

import pytest

import google_sheets_lote as lote


HEADERS = [
    "Setor",
    "Tipo de Patrimônio",
    "Nº de Patrimônio",
    "Fabricante",
    "Data Cadastro",
    "Código de Barras",
]
ROW = ["Almoxarifado", "CPU", "PAT-001", "Dell", "01/10/2026 10:00:00", ""]


class PlanilhaFalsa:
    def __init__(self, falhas: set[str] | None = None):
        self.falhas = falhas or []
        self.chamadas = []

    def values_batch_get(self, ranges, params=None):
        raise ValueError("Aba inexistente no lote")

    def values_get(self, intervalo, params=None):
        self.chamadas.append(intervalo)
        if any(nome in intervalo for nome in self.falhas):
            raise ValueError(f"Intervalo inválido: {intervalo}")
        return {"range": intervalo, "values": [HEADERS, ROW]}


@pytest.fixture(autouse=True)
def limpar_cache():
    clear = getattr(lote._carregar_lote_cache, "clear", None)
    if clear:
        clear()
    yield
    if clear:
        clear()


def test_falha_de_uma_aba_nao_impede_leitura_das_demais(monkeypatch):
    planilha = PlanilhaFalsa(falhas={"URS Jacaraípe"})
    monkeypatch.setattr(lote, "conectar_google_sheets", lambda: planilha)

    resultado = lote.carregar_dados_excel_lote(
        ["URS Jacaraípe", "UBS André Carloni"]
    )

    df_jacaraipe, origem_jacaraipe = resultado["URS Jacaraípe"]
    df_ubs, origem_ubs = resultado["UBS André Carloni"]

    assert len(df_jacaraipe) == 1
    assert "URS Jacara_pe" in origem_jacaraipe
    assert len(df_ubs) == 1
    assert "FALHA DE LEITURA" not in origem_ubs


def test_falha_total_de_uma_unidade_fica_explicita(monkeypatch):
    planilha = PlanilhaFalsa(falhas={"URS Jacaraípe", "URS Jacara_pe"})
    monkeypatch.setattr(lote, "conectar_google_sheets", lambda: planilha)

    resultado = lote.carregar_dados_excel_lote(
        ["URS Jacaraípe", "UBS André Carloni"]
    )

    df_jacaraipe, origem_jacaraipe = resultado["URS Jacaraípe"]
    df_ubs, _ = resultado["UBS André Carloni"]

    assert df_jacaraipe.empty
    assert "FALHA DE LEITURA" in origem_jacaraipe
    assert len(df_ubs) == 1
