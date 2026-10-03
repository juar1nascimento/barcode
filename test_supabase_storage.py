"""Testes unitários locais do processamento de imagens.

Não acessa Supabase, PostgreSQL ou Secrets. Portanto, pode rodar no CI
sem expor credenciais nem criar objetos reais.
"""

import io

from PIL import Image

from supabase_storage import MAX_STORAGE_BYTES, _normalizar_jpeg


def test_normalizar_jpeg_reduz_e_corrige_orientacao():
    imagem = Image.new("RGB", (3000, 2000), "white")
    bruto = io.BytesIO()
    imagem.save(bruto, format="PNG")

    jpeg, largura, altura = _normalizar_jpeg(bruto.getvalue())

    assert jpeg[:2] == b"\xff\xd8"
    assert len(jpeg) <= MAX_STORAGE_BYTES
    assert largura <= 1600
    assert altura <= 1600
    assert largura > 0
    assert altura > 0


from unittest.mock import Mock


class _FakeCursor:
    def __init__(self, results=None, error_on_insert=False):
        self.results = list(results or [])
        self.error_on_insert = error_on_insert
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))
        if self.error_on_insert and "INSERT INTO public.patrimonio_fotos" in query:
            raise RuntimeError("falha simulada no INSERT")

    def fetchone(self):
        if not self.results:
            return None
        return self.results.pop(0)


class _FakeConnection:
    def __init__(self, cursors):
        self.cursors = list(cursors)
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return self.cursors.pop(0)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def test_salvar_foto_patrimonio_fluxo_sucesso(monkeypatch):
    import supabase_storage

    monkeypatch.setattr(
        supabase_storage,
        "_config_supabase",
        lambda: {"url": "https://example.supabase.co", "key": "secret"},
    )
    monkeypatch.setattr(
        supabase_storage,
        "_normalizar_jpeg",
        lambda data: (b"jpeg-data", 1200, 800),
    )
    monkeypatch.setattr(
        supabase_storage,
        "_upload_storage",
        Mock(),
    )
    monkeypatch.setattr(
        supabase_storage,
        "_delete_storage",
        Mock(),
    )

    conn = _FakeConnection(
        [
            _FakeCursor([(1,)]),
            _FakeCursor([(1,), (1,)]),
            _FakeCursor([(7,)]),
        ]
    )

    ok, foto_id, mensagem = supabase_storage.salvar_foto_patrimonio(
        conn, 1, b"imagem", "original.png"
    )

    assert ok is True
    assert foto_id == 7
    assert "Foto 1 gravada" in mensagem
    assert conn.commit_count == 1
    assert conn.rollback_count == 0
    supabase_storage._upload_storage.assert_called_once()
    upload_args = supabase_storage._upload_storage.call_args.args
    assert upload_args[2].startswith("1/foto-001-")
    assert upload_args[2].endswith(".jpg")
    assert upload_args[3] == b"jpeg-data"
    supabase_storage._delete_storage.assert_not_called()


def test_salvar_foto_patrimonio_remove_orfao_se_insert_falhar(monkeypatch):
    import supabase_storage

    monkeypatch.setattr(
        supabase_storage,
        "_config_supabase",
        lambda: {"url": "https://example.supabase.co", "key": "secret"},
    )
    monkeypatch.setattr(
        supabase_storage,
        "_normalizar_jpeg",
        lambda data: (b"jpeg-data", 1200, 800),
    )
    monkeypatch.setattr(supabase_storage, "_upload_storage", Mock())
    monkeypatch.setattr(supabase_storage, "_delete_storage", Mock())

    conn = _FakeConnection(
        [
            _FakeCursor([(1,)]),
            _FakeCursor([(1,), (1,)]),
            _FakeCursor(error_on_insert=True),
        ]
    )

    ok, foto_id, mensagem = supabase_storage.salvar_foto_patrimonio(
        conn, 1, b"imagem", "original.png"
    )

    assert ok is False
    assert foto_id is None
    assert "Não foi possível concluir o armazenamento da foto." in mensagem
    assert conn.commit_count == 0
    assert conn.rollback_count >= 1
    supabase_storage._upload_storage.assert_called_once()
    supabase_storage._delete_storage.assert_called_once()
    delete_args = supabase_storage._delete_storage.call_args.args
    assert delete_args[2].startswith("1/foto-001-")
    assert delete_args[2].endswith(".jpg")
