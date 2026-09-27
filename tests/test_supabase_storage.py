import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import supabase_storage as storage


def _jpeg_bytes(width=120, height=80, color=(120, 80, 40)):
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_config_prefere_secret_key_a_chave_legacy(monkeypatch):
    monkeypatch.setattr(
        storage.st,
        "secrets",
        {
            "supabase": {
                "url": "https://example.supabase.co/",
                "secret_key": "sb_secret_nova",
                "service_role_key": "legacy",
            }
        },
    )

    assert storage._config_supabase() == {
        "url": "https://example.supabase.co",
        "key": "sb_secret_nova",
    }


def test_config_aceita_service_role_como_compatibilidade(monkeypatch):
    monkeypatch.setattr(
        storage.st,
        "secrets",
        {
            "supabase": {
                "url": "https://example.supabase.co/",
                "service_role_key": "legacy",
            }
        },
    )

    assert storage._config_supabase()["key"] == "legacy"


def test_config_rejeita_secret_incompleto(monkeypatch):
    monkeypatch.setattr(
        storage.st,
        "secrets",
        {"supabase": {"url": "https://example.supabase.co/"}},
    )

    try:
        storage._config_supabase()
    except RuntimeError as exc:
        assert "secret_key" in str(exc)
    else:
        raise AssertionError("Configuração incompleta deveria falhar.")


def test_normalizacao_jpeg_rejeita_bytes_vazios():
    try:
        storage._normalizar_jpeg(b"")
    except ValueError as exc:
        assert "vazia" in str(exc)
    else:
        raise AssertionError("Imagem vazia deveria falhar.")


def test_normalizacao_jpeg_corrige_dimensao_e_fica_abaixo_do_limite():
    dados, largura, altura = storage._normalizar_jpeg(_jpeg_bytes(320, 180))

    assert dados.startswith(b"\xff\xd8")
    assert len(dados) <= storage.MAX_STORAGE_BYTES
    assert (largura, altura) == (320, 180)


def test_normalizacao_jpeg_reduz_imagem_grande():
    dados, largura, altura = storage._normalizar_jpeg(_jpeg_bytes(2400, 1600))

    assert dados.startswith(b"\xff\xd8")
    assert len(dados) <= storage.MAX_STORAGE_BYTES
    assert max(largura, altura) <= storage.MAX_DIMENSION


def test_headers_mantem_chave_fora_do_url():
    headers = storage._headers("sb_secret_teste", "image/jpeg")

    assert headers["Authorization"] == "Bearer sb_secret_teste"
    assert headers["apikey"] == "sb_secret_teste"
    assert headers["Content-Type"] == "image/jpeg"


def test_storage_url_usa_bucket_oficial():
    assert (
        storage._storage_url("https://example.supabase.co", "7/foto.jpg")
        == "https://example.supabase.co/storage/v1/object/patrimonio-fotos/7/foto.jpg"
    )


def test_upload_storage_envia_jpeg_e_timeout(monkeypatch):
    chamadas = []

    class Response:
        ok = True
        status_code = 200

    def fake_post(url, headers, data, timeout):
        chamadas.append((url, headers, data, timeout))
        return Response()

    monkeypatch.setattr(storage.requests, "post", fake_post)

    storage._upload_storage(
        "https://example.supabase.co",
        "sb_secret_teste",
        "7/foto.jpg",
        b"jpeg",
    )

    assert chamadas[0][0].endswith("/storage/v1/object/patrimonio-fotos/7/foto.jpg")
    assert chamadas[0][1]["Content-Type"] == "image/jpeg"
    assert chamadas[0][2] == b"jpeg"
    assert chamadas[0][3] == 30


def test_upload_storage_transforma_http_em_erro(monkeypatch):
    class Response:
        ok = False
        status_code = 413

    monkeypatch.setattr(storage.requests, "post", lambda *args, **kwargs: Response())

    try:
        storage._upload_storage(
            "https://example.supabase.co",
            "sb_secret_teste",
            "7/foto.jpg",
            b"jpeg",
        )
    except RuntimeError as exc:
        assert "HTTP 413" in str(exc)
    else:
        raise AssertionError("Falha HTTP deveria ser propagada como RuntimeError.")
