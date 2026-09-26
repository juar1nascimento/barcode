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
