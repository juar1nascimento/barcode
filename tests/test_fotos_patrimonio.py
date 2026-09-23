import io

import pytest

import postgresql_persistencia as pg


def test_preparar_foto_reduz_e_comprime():
    from PIL import Image

    imagem = Image.new("RGB", (3200, 2400), "white")
    bruto = io.BytesIO()
    imagem.save(bruto, format="PNG")

    dados, largura, altura, sha256 = pg.preparar_foto_patrimonio(bruto.getvalue())

    assert largura <= 1600
    assert altura <= 1600
    assert len(dados) <= pg.MAX_FOTO_BYTES
    assert len(sha256) == 64
    assert len(dados) > 0


def test_preparar_foto_rejeita_arquivo_vazio():
    with pytest.raises(ValueError):
        pg.preparar_foto_patrimonio(b"")
