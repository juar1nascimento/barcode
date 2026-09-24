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


def test_montar_registro_foto_usa_serial_como_nome():
    item = pg.montar_registro_foto("SERIAL-001", b"abc", 10, 20, "a" * 64)
    assert item["nome"] == "SERIAL-001"
    assert item["arquivo_nome"] == "SERIAL-001.jpg"
    assert item["tamanho_bytes"] == 3
    assert item["imagem_base64"] == "YWJj"


def test_normalizar_sequencia_fotos_preserva_ordem_e_nomes():
    fotos = [
        {"nome": "SERIAL-001", "imagem_base64": "AAA"},
        {"nome": "SERIAL-002", "imagem_base64": "BBB"},
    ]

    resultado = pg.normalizar_sequencia_fotos(fotos)

    assert [item["nome"] for item in resultado] == ["SERIAL-001", "SERIAL-002"]
    assert [item["ordem"] for item in resultado] == [1, 2]
    assert [item["arquivo_nome"] for item in resultado] == ["SERIAL-001.jpg", "SERIAL-002.jpg"]


def test_normalizar_sequencia_fotos_vazia():
    assert pg.normalizar_sequencia_fotos(None) == []
    assert pg.normalizar_sequencia_fotos([]) == []


def test_normalizar_sequencia_fotos_rejeita_item_invalido():
    with pytest.raises(ValueError):
        pg.normalizar_sequencia_fotos([{"nome": "", "imagem_base64": "AAA"}])


def test_normalizar_sequencia_fotos_adiciona_ordem_a_registros_legados():
    fotos = [{"nome": "SERIAL-X", "imagem_base64": "AAA", "arquivo_nome": "SERIAL-X.jpg"}]
    resultado = pg.normalizar_sequencia_fotos(fotos)
    assert resultado[0]["ordem"] == 1
    assert resultado[0]["arquivo_nome"] == "SERIAL-X.jpg"
