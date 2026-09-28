"""Persistência isolada de fotos de patrimônio no Supabase Storage.

Este módulo não altera a interface do sistema. Ele prepara o fluxo:
bytes da imagem -> normalização/compressão -> Storage privado ->
metadados em public.patrimonio_fotos.

A chave Supabase é lida exclusivamente de Streamlit Secrets e nunca é
retornada, exibida ou registrada em log.
"""

from __future__ import annotations

import gc
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
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_INPUT_PIXELS = 20_000_000
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
    if len(image_bytes) > MAX_INPUT_BYTES:
        raise ValueError(
            f"A imagem original excede o limite de {MAX_INPUT_BYTES // (1024 * 1024)} MB."
        )

    with Image.open(io.BytesIO(image_bytes)) as original:
        largura_original, altura_original = original.size
        if largura_original * altura_original > MAX_INPUT_PIXELS:
            raise ValueError(
                "A imagem possui resolução excessiva para processamento seguro. "
                f"Limite: {MAX_INPUT_PIXELS:,} pixels."
            )

        if original.format == "JPEG":
            original.draft("RGB", (MAX_DIMENSION, MAX_DIMENSION))

        image = ImageOps.exif_transpose(original)
        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
        if image.mode != "RGB":
            image = image.convert("RGB")

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

        resultado = (melhor, image.width, image.height)
        gc.collect()
        return resultado


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


def listar_objetos_bucket() -> Tuple[bool, list, str]:
    """Lista recursivamente os arquivos do bucket sem modificar o Storage."""
    try:
        config = _config_supabase()
        encontrados = []

        def listar_prefixo(prefixo: str) -> None:
            offset = 0
            while True:
                response = requests.post(
                    f"{config['url']}/storage/v1/object/list/{BUCKET}",
                    headers={**_headers(config["key"]), "Content-Type": "application/json"},
                    json={
                        "prefix": prefixo,
                        "limit": 1000,
                        "offset": offset,
                        "sortBy": {"column": "name", "order": "asc"},
                    },
                    timeout=30,
                )
                if not response.ok:
                    raise RuntimeError(f"HTTP {response.status_code}")
                itens = response.json()
                if not itens:
                    break

                for item in itens:
                    nome = str(item.get("name") or "").strip()
                    if not nome:
                        continue
                    caminho = f"{prefixo.rstrip('/')}/{nome}" if prefixo else nome
                    if item.get("id") is None:
                        listar_prefixo(caminho)
                    else:
                        encontrados.append(caminho)

                if len(itens) < 1000:
                    break
                offset += len(itens)

        listar_prefixo("")
        return True, sorted(set(encontrados)), "Storage consultado."
    except Exception as exc:
        return False, [], f"Falha ao listar o Storage: {exc}"


def excluir_objetos_patrimonio(fotos) -> Tuple[bool, str]:
    """Remove objetos de fotos do Storage; não altera o banco de dados."""
    fotos = list(fotos or [])
    if not fotos:
        return True, "Nenhum objeto de foto para remover."

    try:
        config = _config_supabase()
        caminhos = []
        for bucket, path in fotos:
            if str(bucket) != BUCKET:
                return False, f"Bucket de foto não permitido: {bucket}."
            caminhos.append(str(path))

        response = requests.delete(
            f"{config['url']}/storage/v1/object/{BUCKET}",
            headers={**_headers(config["key"]), "Content-Type": "application/json"},
            json={"prefixes": caminhos},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}")
        return True, f"{len(caminhos)} objeto(s) removido(s) do Storage."
    except Exception as exc:
        return False, f"Falha ao remover objetos do Storage: {exc}"


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



def criar_urls_assinadas_fotos(caminhos, expires_in: int = 900) -> Tuple[bool, dict, str]:
    """Cria URLs temporárias para fotos do bucket privado."""
    caminhos = [str(p).strip() for p in (caminhos or []) if str(p).strip()]
    if not caminhos:
        return True, {}, "Nenhuma foto."
    try:
        config = _config_supabase()
        response = requests.post(
            f"{config['url']}/storage/v1/object/sign/{BUCKET}",
            headers={**_headers(config["key"]), "Content-Type": "application/json"},
            json={"paths": caminhos, "expiresIn": int(expires_in)},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}")
        itens = response.json()
        urls = {}
        for item in itens:
            path = str(item.get("path") or "").strip()
            token = str(item.get("signedURL") or item.get("signedUrl") or "").strip()
            if path and token:
                urls[path] = (
                    token if token.startswith("http")
                    else f"{config['url']}/storage/v1{token}"
                )
        return True, urls, "URLs temporárias geradas."
    except Exception as exc:
        return False, {}, f"Falha ao gerar URLs das fotos: {exc}"



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
