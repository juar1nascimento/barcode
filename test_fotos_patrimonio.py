from unittest.mock import patch

from fotos_patrimonio import _coluna_letra, _url_publica_foto


def test_coluna_letra_converte_indices_para_a1():
    assert _coluna_letra(1) == "A"
    assert _coluna_letra(26) == "Z"
    assert _coluna_letra(27) == "AA"
    assert _coluna_letra(36) == "AJ"


def test_url_publica_foto_usa_url_assinada_sem_expor_credencial(monkeypatch):
    from fotos_patrimonio import criar_url_assinada_storage

    monkeypatch.setattr(
        "fotos_patrimonio.criar_url_assinada_storage",
        lambda bucket, path, expires_in: "https://example.supabase.co/storage/v1/object/sign/patrimonio-fotos/abc?token=temporario",
    )
    url = _url_publica_foto("patrimonio/123/foto 001.jpg")

    assert url.startswith("https://example.supabase.co/storage/v1/object/sign/")
    assert "secret_key" not in url


def test_worker_sheet_url_usa_url_assinada(monkeypatch):
    import sheets_outbox_worker as worker

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    class Response:
        ok = True
        def json(self):
            return {"signedURL": "/storage/v1/object/sign/patrimonio-fotos/abc?token=test"}
    monkeypatch.setattr(worker.requests, "post", lambda *args, **kwargs: Response())
    assert worker.sheet_url("patrimonio/1/foto 001.jpg").startswith(
        "https://example.supabase.co/storage/v1/object/sign/"
    )


def test_intervalo_colunas_foto_nao_sobrescreve_id_patrimonio():
    from fotos_patrimonio import _intervalo_colunas_foto

    cabecalho = [
        "Setor", "Tipo de Patrimônio", "Nº de Patrimônio",
        "Fabricante", "Data Cadastro", "ID Patrimônio",
        *[f"Foto {i}" for i in range(1, 11)],
    ]
    primeira, ultima = _intervalo_colunas_foto(cabecalho)

    assert _coluna_letra(primeira) == "G"
    assert _coluna_letra(ultima) == "P"
