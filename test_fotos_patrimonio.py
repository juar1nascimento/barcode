from unittest.mock import patch

from fotos_patrimonio import _coluna_letra, _url_publica_foto


def test_coluna_letra_converte_indices_para_a1():
    assert _coluna_letra(1) == "A"
    assert _coluna_letra(26) == "Z"
    assert _coluna_letra(27) == "AA"
    assert _coluna_letra(36) == "AJ"


def test_url_publica_foto_codifica_caminho_sem_expor_credencial():
    with patch(
        "fotos_patrimonio.st.secrets",
        {"supabase": {"url": "https://example.supabase.co", "secret_key": "nao-deve-aparecer"}},
    ):
        url = _url_publica_foto("patrimonio/123/foto 001.jpg")

    assert url == (
        "https://example.supabase.co/storage/v1/object/public/"
        "patrimonio-fotos/patrimonio/123/foto%20001.jpg"
    )
    assert "secret_key" not in url


def test_worker_sheet_url_preserva_caminho_e_codifica_espacos(monkeypatch):
    import sheets_outbox_worker as worker

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    assert worker.sheet_url("patrimonio/1/foto 001.jpg") == (
        "https://example.supabase.co/storage/v1/object/public/"
        "patrimonio-fotos/patrimonio/1/foto%20001.jpg"
    )
