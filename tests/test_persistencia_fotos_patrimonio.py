from __future__ import annotations

from dataclasses import dataclass

import pytest

from persistencia_fotos_patrimonio import (
    MAX_UPLOAD_BYTES,
    FotoPatrimonioPersistenciaError,
    salvar_foto_patrimonio,
)
from processamento_fotos_patrimonio import FotoProcessada


def foto_teste(tamanho: int = 100) -> FotoProcessada:
    return FotoProcessada(
        conteudo=b"x" * tamanho,
        arquivo_nome="foto.jpg",
        mime_type="image/jpeg",
        tamanho_bytes=tamanho,
        largura=1200,
        altura=800,
        sha256="a" * 64,
    )


def test_rejeita_foto_acima_do_limite_do_bucket(monkeypatch):
    monkeypatch.setattr(
        "persistencia_fotos_patrimonio.validar_acesso_fotos",
        lambda: pytest.fail("não deveria acessar o Supabase"),
    )
    with pytest.raises(FotoPatrimonioPersistenciaError):
        salvar_foto_patrimonio(2, foto_teste(MAX_UPLOAD_BYTES + 1))


def test_rejeita_patrimonio_invalido(monkeypatch):
    monkeypatch.setattr(
        "persistencia_fotos_patrimonio.validar_acesso_fotos",
        lambda: pytest.fail("não deveria acessar o Supabase"),
    )
    with pytest.raises(FotoPatrimonioPersistenciaError):
        salvar_foto_patrimonio(0, foto_teste())


@dataclass
class Resposta:
    data: list


class FakeQuery:
    def __init__(self, data):
        self.data = data

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return Resposta(self.data)


class FakeTable:
    def __init__(self, ordem=3):
        self.ordem = ordem
        self.insertado = None

    def select(self, *_args):
        return FakeQuery([{"id": 2}] if _args and _args[0] == "id" else [{"ordem": self.ordem}])

    def eq(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def insert(self, payload):
        self.insertado = payload
        return FakeQuery([])


class FakeStorage:
    def __init__(self):
        self.uploads = []
        self.removals = []

    def from_(self, bucket):
        self.bucket = bucket
        return self

    def upload(self, path, content, options):
        self.uploads.append((path, content, options))

    def remove(self, paths):
        self.removals.append(paths)


class FakeClient:
    def __init__(self):
        self.table_fotos = FakeTable(3)
        self.table_patrimonios = FakeTable()
        self.storage = FakeStorage()

    def table(self, name):
        return self.table_fotos if name == "patrimonio_fotos" else self.table_patrimonios


def test_persiste_foto_com_ordem_e_path_unico(monkeypatch):
    cliente = FakeClient()
    monkeypatch.setattr(
        "persistencia_fotos_patrimonio.validar_acesso_fotos",
        lambda: cliente,
    )

    resultado = salvar_foto_patrimonio(2, foto_teste())

    assert resultado.sucesso is True
    assert resultado.ordem == 4
    assert resultado.storage_path.startswith("patrimonio/2/foto-")
    assert resultado.storage_path.endswith(".jpg")
    assert cliente.storage.uploads[0][2]["upsert"] is False
    assert cliente.table_fotos.insertado["ordem"] == 4
    assert cliente.table_fotos.insertado["patrimonio_id"] == 2
