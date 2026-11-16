import projecao_almoxarifado as modulo


def test_estatisticas_eventos_separam_eventos_sem_meta(monkeypatch):
    ultimo_evento = "2026-10-29T16:04:30+00:00"
    monkeypatch.setattr(
        modulo,
        "_query",
        lambda sql, params=(): [(45, 45, 42, 43, ultimo_evento)],
    )

    resultado = modulo._estatisticas_eventos()

    assert resultado == {
        "eventos_total": 45,
        "encontrados": 45,
        "patrimonios_distintos": 42,
        "encontrados_sem_meta": 43,
        "ultimo_evento": ultimo_evento,
    }


def test_estatisticas_eventos_normalizam_valores_nulos(monkeypatch):
    monkeypatch.setattr(modulo, "_query", lambda sql, params=(): [(None, None, None, None, None)])

    resultado = modulo._estatisticas_eventos()

    assert resultado == {
        "eventos_total": 0,
        "encontrados": 0,
        "patrimonios_distintos": 0,
        "encontrados_sem_meta": 0,
        "ultimo_evento": None,
    }
