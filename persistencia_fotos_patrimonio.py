"""Persistência server-side de fotos de patrimônio no Supabase.

A operação é chamada somente após o cadastro do patrimônio obter seu ID.
A imagem já deve ter sido processada por processamento_fotos_patrimonio.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from processamento_fotos_patrimonio import FotoProcessada
from supabase_fotos_patrimonio import validar_acesso_fotos

BUCKET = "patrimonio-fotos"
MAX_UPLOAD_BYTES = 1_048_576


class FotoPatrimonioPersistenciaError(RuntimeError):
    """Falha controlada na persistência da foto."""


@dataclass(frozen=True)
class ResultadoFotoPatrimonio:
    sucesso: bool
    ordem: int | None = None
    storage_path: str | None = None
    mensagem: str = ""


def _proxima_ordem(cliente, patrimonio_id: int) -> int:
    resposta = (
        cliente.table("patrimonio_fotos")
        .select("ordem")
        .eq("patrimonio_id", patrimonio_id)
        .order("ordem", desc=True)
        .limit(1)
        .execute()
    )
    registros = resposta.data or []
    return (int(registros[0]["ordem"]) + 1) if registros else 1


def _patrimonio_existe(cliente, patrimonio_id: int) -> bool:
    resposta = (
        cliente.table("patrimonios")
        .select("id")
        .eq("id", patrimonio_id)
        .limit(1)
        .execute()
    )
    return bool(resposta.data)


def _remover_objeto(cliente, path: str) -> bool:
    try:
        cliente.storage.from_(BUCKET).remove([path])
        return True
    except Exception:
        # O erro original é mais importante; a rotina nunca expõe segredo.
        return False


def salvar_foto_patrimonio(
    patrimonio_id: int,
    foto: FotoProcessada,
    *,
    max_tentativas_ordem: int = 3,
) -> ResultadoFotoPatrimonio:
    """Envia uma foto e registra seus metadados, sem sobrescrever arquivos.

    A unicidade do banco em (patrimonio_id, ordem) protege contra concorrência.
    Em caso de colisão, o objeto recém-enviado é removido e uma nova ordem é
    tentada. Se o INSERT de metadados falhar por outro motivo, o objeto também
    é removido para evitar órfãos no Storage.
    """
    if not isinstance(patrimonio_id, int) or patrimonio_id < 1:
        raise FotoPatrimonioPersistenciaError("patrimonio_id inválido.")
    if foto.tamanho_bytes <= 0 or foto.tamanho_bytes > MAX_UPLOAD_BYTES:
        raise FotoPatrimonioPersistenciaError("A foto excede o limite do bucket.")
    if foto.mime_type != "image/jpeg":
        raise FotoPatrimonioPersistenciaError("A foto deve estar normalizada como JPEG.")

    cliente = validar_acesso_fotos()

    if not _patrimonio_existe(cliente, patrimonio_id):
        raise FotoPatrimonioPersistenciaError("Patrimônio não encontrado.")

    ultimo_erro: Exception | None = None

    for _ in range(max_tentativas_ordem):
        ordem = _proxima_ordem(cliente, patrimonio_id)
        storage_path = f"patrimonio/{patrimonio_id}/foto-{uuid4().hex}.jpg"

        try:
            cliente.storage.from_(BUCKET).upload(
                storage_path,
                foto.conteudo,
                {
                    "content-type": foto.mime_type,
                    "cache-control": "3600",
                    "upsert": False,
                },
            )
        except Exception as exc:
            raise FotoPatrimonioPersistenciaError(
                "Não foi possível enviar a foto ao Storage."
            ) from exc

        try:
            cliente.table("patrimonio_fotos").insert(
                {
                    "patrimonio_id": patrimonio_id,
                    "ordem": ordem,
                    "storage_bucket": BUCKET,
                    "storage_path": storage_path,
                    "arquivo_nome": foto.arquivo_nome,
                    "mime_type": foto.mime_type,
                    "tamanho_bytes": foto.tamanho_bytes,
                    "largura": foto.largura,
                    "altura": foto.altura,
                    "sha256": foto.sha256,
                }
            ).execute()
        except Exception as exc:
            ultimo_erro = exc
            _remover_objeto(cliente, storage_path)
            # Colisão na restrição única (patrimonio_id, ordem): recalcula.
            mensagem = str(exc).lower()
            if "uq_patrimonio_fotos_ordem" in mensagem or "duplicate key" in mensagem:
                continue
            if objeto_removido:
                detalhe = "O objeto foi removido para evitar arquivo órfão."
            else:
                detalhe = (
                    "Não foi possível remover o objeto; será necessário verificar "
                    "o Storage para evitar arquivo órfão."
                )
            raise FotoPatrimonioPersistenciaError(
                "A foto foi enviada, mas o registro dos metadados falhou. "
                + detalhe
            ) from exc

        return ResultadoFotoPatrimonio(
            sucesso=True,
            ordem=ordem,
            storage_path=storage_path,
            mensagem=f"Foto {ordem} registrada com sucesso.",
        )

    raise FotoPatrimonioPersistenciaError(
        "Não foi possível reservar uma ordem exclusiva para a foto."
    ) from ultimo_erro
