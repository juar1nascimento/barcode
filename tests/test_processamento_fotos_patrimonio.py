from io import BytesIO
from hashlib import sha256

import pytest
from PIL import Image

from processamento_fotos_patrimonio import FotoPatrimonioError, processar_foto_patrimonio


def imagem_bytes(tamanho=(3000, 2200), cor=(80, 120, 160), formato="JPEG"):
    imagem = Image.new("RGB", tamanho, cor)
    buffer = BytesIO()
    imagem.save(buffer, format=formato, quality=95)
    return buffer.getvalue()


def test_processa_e_limita_tamanho():
    resultado = processar_foto_patrimonio(imagem_bytes())
    assert resultado.mime_type == "image/jpeg"
    assert resultado.tamanho_bytes <= 950_000
    assert resultado.largura <= 2048
    assert resultado.altura <= 2048
    assert len(resultado.sha256) == 64
    assert resultado.sha256 == sha256(resultado.conteudo).hexdigest()


def test_corrige_orientacao_exif_e_preserva_proporcao():
    resultado = processar_foto_patrimonio(imagem_bytes((4000, 2000)), max_dimension=1600)
    assert resultado.largura == 1600
    assert resultado.altura == 800


def test_aceita_png_e_normaliza_para_jpeg():
    resultado = processar_foto_patrimonio(imagem_bytes((1000, 700), formato="PNG"))
    assert resultado.arquivo_nome == "foto.jpg"
    assert resultado.mime_type == "image/jpeg"
    with Image.open(BytesIO(resultado.conteudo)) as imagem:
        assert imagem.format == "JPEG"
        assert imagem.mode == "RGB"


def test_rejeita_arquivo_vazio():
    with pytest.raises(FotoPatrimonioError):
        processar_foto_patrimonio(b"")


def test_rejeita_conteudo_invalido():
    with pytest.raises(FotoPatrimonioError):
        processar_foto_patrimonio(b"nao e uma imagem")
