import io

import pytest
from PIL import Image, UnidentifiedImageError

import supabase_storage as storage


def _jpeg_bytes(size=(2400, 1800), quality=95, exif=None):
    image = Image.new("RGB", size, (120, 140, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, exif=exif or b"")
    return buffer.getvalue()


def test_photo_normalization_produces_jpeg_within_storage_limit():
    data, width, height = storage._normalizar_jpeg(_jpeg_bytes())

    assert data.startswith(b"\xff\xd8\xff")
    assert len(data) <= storage.MAX_STORAGE_BYTES
    assert width > 0 and height > 0


def test_photo_normalization_rejects_input_above_hard_limit():
    oversized = b"0" * (storage.MAX_INPUT_BYTES + 1)

    with pytest.raises(ValueError, match="limite"):
        storage._normalizar_jpeg(oversized)


def test_photo_normalization_applies_exif_orientation():
    exif = Image.Exif()
    exif[274] = 6  # Rotate 90 degrees clockwise when displayed.
    normalized, width, height = storage._normalizar_jpeg(
        _jpeg_bytes(size=(120, 60), exif=exif)
    )

    assert normalized.startswith(b"\xff\xd8\xff")
    assert (width, height) == (60, 120)


def test_photo_normalization_caps_extreme_dimensions():
    normalized, width, height = storage._normalizar_jpeg(
        _jpeg_bytes(size=(4000, 3000))
    )

    assert normalized.startswith(b"\xff\xd8\xff")
    assert max(width, height) <= storage.MAX_DIMENSION
    assert len(normalized) <= storage.MAX_STORAGE_BYTES


def test_photo_normalization_rejects_invalid_image_bytes():
    with pytest.raises((UnidentifiedImageError, OSError)):
        storage._normalizar_jpeg(b"not an image")
