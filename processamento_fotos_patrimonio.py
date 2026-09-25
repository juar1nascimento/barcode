from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError

DEFAULT_MAX_DIMENSION = 2048
DEFAULT_TARGET_BYTES = 950_000
DEFAULT_INITIAL_QUALITY = 88
DEFAULT_MIN_QUALITY = 65
DEFAULT_MIN_DIMENSION = 640


class FotoPatrimonioError(ValueError):
    """Erro de validação/processamento de uma foto de patrimônio."""


@dataclass(frozen=True)
class FotoProcessada:
    """Resultado final pronto para a etapa de upload."""

    conteudo: bytes
    arquivo_nome: str
    mime_type: str
    tamanho_bytes: int
    largura: int
    altura: int
    sha256: str


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue()


def processar_foto_patrimonio(
    origem: bytes | bytearray | memoryview | BinaryIO,
    *,
    max_dimension: int = DEFAULT_MAX_DIMENSION,
    target_bytes: int = DEFAULT_TARGET_BYTES,
    initial_quality: int = DEFAULT_INITIAL_QUALITY,
    min_quality: int = DEFAULT_MIN_QUALITY,
    min_dimension: int = DEFAULT_MIN_DIMENSION,
) -> FotoProcessada:
    """Normaliza, redimensiona e comprime uma foto para uso no Storage."""
    if max_dimension < 1 or target_bytes < 1 or min_dimension < 1:
        raise FotoPatrimonioError("Parâmetros de dimensão/tamanho inválidos.")
    if not 1 <= min_quality <= 95 or not 1 <= initial_quality <= 95:
        raise FotoPatrimonioError("Qualidade deve estar entre 1 e 95.")
    if min_quality > initial_quality:
        raise FotoPatrimonioError("min_quality não pode superar initial_quality.")

    if isinstance(origem, (bytes, bytearray, memoryview)):
        raw = bytes(origem)
    elif hasattr(origem, "read"):
        raw = origem.read()
    else:
        raise FotoPatrimonioError("A origem deve ser bytes ou um arquivo binário.")

    if not raw:
        raise FotoPatrimonioError("A imagem recebida está vazia.")

    try:
        with Image.open(BytesIO(raw)) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
            if image.mode != "RGB":
                image = image.convert("RGB")
            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            del raw

            quality = initial_quality
            encoded = _encode_jpeg(image, quality)

            while len(encoded) > target_bytes:
                if quality > min_quality:
                    quality = max(min_quality, quality - 5)
                    encoded = _encode_jpeg(image, quality)
                    continue

                width, height = image.size
                menor_lado = min(width, height)
                escala = max(0.85, min_dimension / menor_lado)
                if escala >= 1:
                    break
                next_width = max(1, int(round(width * escala)))
                next_height = max(1, int(round(height * escala)))
                if (next_width, next_height) == (width, height):
                    break
                image = image.resize((next_width, next_height), Image.Resampling.LANCZOS)
                quality = initial_quality
                encoded = _encode_jpeg(image, quality)

            largura, altura = image.size

        if len(encoded) > target_bytes:
            raise FotoPatrimonioError(
                f"Não foi possível reduzir a imagem para {target_bytes} bytes."
            )

        return FotoProcessada(
            conteudo=encoded,
            arquivo_nome="foto.jpg",
            mime_type="image/jpeg",
            tamanho_bytes=len(encoded),
            largura=largura,
            altura=altura,
            sha256=sha256(encoded).hexdigest(),
        )
    except UnidentifiedImageError as exc:
        raise FotoPatrimonioError("O arquivo recebido não é uma imagem válida.") from exc
    except OSError as exc:
        raise FotoPatrimonioError("Não foi possível decodificar a imagem.") from exc
