"""Persistência isolada de fotos de patrimônio no Supabase Storage.

Este módulo não altera a interface do sistema. Ele prepara o fluxo:
bytes da imagem -> normalização/compressão -> Storage privado ->
metadados em public.patrimonio_fotos.

A chave Supabase é lida exclusivamente de Streamlit Secrets e nunca é
retornada, exibida ou registrada em log.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from typing import Optional, Tuple

import requests
from PIL import Image, ImageOps
import streamlit as st

BUCKET = "patrimonio-fotos"
MAX_STORAGE_BYTES = 1_048_576
TARGET_BYTES = 900_000
MAX_DIMENSION = 1600
JPEG_QUALITY_START = 85
JPEG_QUALITY_MIN = 55


def _config_supabase() -> dict:
    sec = st.secrets.get("supabase")
    if not sec:
        raise RuntimeError("Secret [supabase] não configurada.")

    url = str(sec.get("url") or "").strip().rstrip("/")
    key = str(sec.get("secret_key") or sec.get("service_role_key") or "").strip()

    if not url or not key:
        raise RuntimeError(
            "Configure [supabase].url e [supabase].secret_key "
            "(ou service_role_key) nos Secrets."
        )

    return {"url": url, "key": key}


def _normalizar_jpeg(image_bytes: bytes) -> Tuple[bytes, int, int]:
    if not image_bytes:
        raise ValueError("A imagem recebida está vazia.")

    with Image.open(io.BytesIO(image_bytes)) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

        qualidade = JPEG_QUALITY_START
        melhor = b""

        while True:
            buffer = io.BytesIO()
            image.save(
                buffer,
                format="JPEG",
                quality=qualidade,
                optimize=True,
                progressive=True,
            )
            candidato = buffer.getvalue()
            if not melhor or len(candidato) < len(melhor):
                melhor = candidato

            if len(candidato) <= TARGET_BYTES:
                break
            if qualidade > JPEG_QUALITY_MIN:
                qualidade -= 5
                continue

            largura, altura = image.size
            if max(largura, altura) <= 1000:
                break

            image = image.resize(
                (max(1, round(largura * 0.85)), max(1, round(altura * 0.85))),
                Image.Resampling.LANCZOS,
            )
            qualidade = 75

        if len(melhor) > MAX_STORAGE_BYTES:
            raise ValueError(
                "Não foi possível comprimir a imagem abaixo do limite de 1 MB."
            )

        return melhor, image.width, image.height


def _headers(key: str, content_type: Optional[str] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _storage_url(base_url: str, path: str) -> str:
    return f"{base_url}/storage/v1/object/{BUCKET}/{path}"


def _upload_storage(base_url: str, key: str, path: str, data: bytes) -> None:
    response = requests.post(
        _storage_url(base_url, path),
        headers=_headers(key, "image/jpeg"),
        data=data,
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(
            f"Falha no upload da foto para o Storage (HTTP {response.status_code})."
        )


def _delete_storage(base_url: str, key: str, path: str) -> None:
    response = requests.delete(
        _storage_url(base_url, path),
        headers=_headers(key),
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(
            f"Falha na limpeza do objeto órfão no Storage "
            f"(HTTP {response.status_code})."
        )


def _proxima_ordem(conn, patrimonio_id: int) -> int:
    # Bloqueia o patrimônio durante a escolha da ordem, evitando duas fotos
    # concorrentes receberem a mesma ordem.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM public.patrimonios WHERE id = %s FOR UPDATE",
            (patrimonio_id,),
        )
        if cur.fetchone() is None:
            raise ValueError("Patrimônio não encontrado.")

        cur.execute(
            """SELECT COALESCE(MAX(ordem), 0) + 1
                 FROM public.patrimonio_fotos
                WHERE patrimonio_id = %s""",
            (patrimonio_id,),
        )
        return int(cur.fetchone()[0])


def salvar_foto_patrimonio(
    conn,
    patrimonio_id: int,
    image_bytes: bytes,
    arquivo_nome_original: str = "foto.jpg",
) -> Tuple[bool, Optional[int], str]:
    """Salva uma foto e seus metadados, retornando (sucesso, foto_id, mensagem).

    A função faz upload primeiro e registra os metadados depois. Se o INSERT
    falhar, tenta remover o objeto recém-criado para evitar órfãos.
    """
    if not isinstance(patrimonio_id, int) or patrimonio_id <= 0:
        return False, None, "ID de patrimônio inválido."

    try:
        config = _config_supabase()
        jpeg, largura, altura = _normalizar_jpeg(image_bytes)
        sha256 = hashlib.sha256(jpeg).hexdigest()

        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.patrimonios WHERE id = %s",
                (patrimonio_id,),
            )
            if cur.fetchone() is None:
                return False, None, "Patrimônio não encontrado."

        ordem = _proxima_ordem(conn, patrimonio_id)

        nome_base = f"foto-{ordem:03d}-{uuid.uuid4().hex}.jpg"
        storage_path = f"{patrimonio_id}/{nome_base}"

        _upload_storage(config["url"], config["key"], storage_path, jpeg)

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO public.patrimonio_fotos
                         (patrimonio_id, ordem, storage_bucket, storage_path,
                          arquivo_nome, mime_type, tamanho_bytes, largura,
                          altura, sha256)
                       VALUES (%s, %s, %s, %s, %s, 'image/jpeg', %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        patrimonio_id,
                        ordem,
                        BUCKET,
                        storage_path,
                        arquivo_nome_original or nome_base,
                        len(jpeg),
                        largura,
                        altura,
                        sha256,
                    ),
                )
                foto_id = int(cur.fetchone()[0])
            conn.commit()
            return True, foto_id, f"Foto {ordem} gravada com sucesso."
        except Exception:
            conn.rollback()
            try:
                _delete_storage(config["url"], config["key"], storage_path)
            except Exception:
                pass
            raise

    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, None, f"Falha ao salvar foto: {exc}"
