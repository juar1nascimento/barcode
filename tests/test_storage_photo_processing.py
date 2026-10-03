import io

from PIL import Image

import supabase_storage as storage


def _jpeg_bytes(size=(2400, 1800), quality=95):
    image = Image.new("RGB", size, (120, 140, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def test_photo_normalization_produces_jpeg_within_storage_limit():
    data, width, height = storage._normalizar_jpeg(_jpeg_bytes())

    assert data.startswith(b"\\xff\\xd8\\xff")
    assert len(data) <= storage.MAX_STORAGE_BYTES
    assert width > 0 and height > 0


def test_photo_normalization_rejects_input_above_hard_limit():
    oversized = b"0" * (storage.MAX_INPUT_BYTES + 1)

    try:
        storage._normalizar_jpeg(oversized)
    except ValueError as exc:
        assert "limite" in str(exc).lower()
    else:
        raise AssertionError("imagem acima do limite deveria ser rejeitada")
