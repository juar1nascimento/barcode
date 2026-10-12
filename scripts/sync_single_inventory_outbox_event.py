"""Execução isolada e opt-in de um único evento de inventário para Google Sheets.

Padrão: somente leitura. Para escrever, são exigidos --execute e
--confirm-write. Este utilitário nunca consome a fila de fotos nem outros IDs.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from postgresql_persistencia import conectar
from sincronizador_google_sheets import MAX_TENTATIVAS, _espelhar_patrimonio


def validar_modo(executar: bool, confirmar_escrita: bool) -> None:
    if executar and not confirmar_escrita:
        raise ValueError("Para escrever, informe também --confirm-write.")
    if confirmar_escrita and not executar:
        raise ValueError("--confirm-write só pode ser usado junto com --execute.")


def classificar_falha(tentativas: int, max_tentativas: int = MAX_TENTATIVAS) -> str:
    return "dead_letter" if tentativas >= max_tentativas else "failed"


def inspecionar_evento(event_id: int) -> dict[str, Any]:
    conn = conectar()
    if conn is None:
        raise RuntimeError("PostgreSQL indisponível.")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, patrimonio_id, status, tentativas,
                       (proxima_tentativa_em IS NULL OR proxima_tentativa_em <= now()) AS elegivel_por_tempo
                  FROM public.patrimonios_sheets_outbox
                 WHERE id = %s
                """,
                (event_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise ValueError(f"Evento de inventário {event_id} não encontrado.")
        return {
            "event_id": int(row[0]),
            "patrimonio_id": int(row[1]),
            "status": str(row[2]),
            "tentativas": int(row[3] or 0),
            "elegivel_por_tempo": bool(row[4]),
            "elegivel": (
                str(row[2]) in {"pending", "failed"}
                and bool(row[4])
                and int(row[3] or 0) < MAX_TENTATIVAS
            ),
        }
    finally:
        conn.close()


def executar_evento_unico(event_id: int) -> dict[str, Any]:
    """Claim atômico de um ID exato; nenhuma outra linha é selecionada."""
    conn = conectar()
    if conn is None:
        raise RuntimeError("PostgreSQL indisponível.")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.patrimonios_sheets_outbox
                   SET status = 'processing',
                       processando_em = now(),
                       tentativas = COALESCE(tentativas, 0) + 1,
                       atualizado_em = now()
                 WHERE id = %s
                   AND status IN ('pending', 'failed')
                   AND (proxima_tentativa_em IS NULL OR proxima_tentativa_em <= now())
                   AND COALESCE(tentativas, 0) < %s
                RETURNING id, patrimonio_id, tentativas
                """,
                (event_id, MAX_TENTATIVAS),
            )
            claimed = cur.fetchone()
        if claimed is None:
            conn.rollback()
            estado = inspecionar_evento(event_id)
            raise RuntimeError(
                "Evento não elegível para claim isolado; nenhum evento foi processado. "
                + json.dumps(estado, ensure_ascii=False)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    patrimonio_id = int(claimed[1])
    tentativas = int(claimed[2])
    try:
        # Só retorna depois da escrita e releitura dos seis campos.
        _espelhar_patrimonio({"patrimonio_id": patrimonio_id})
    except Exception as exc:
        status = classificar_falha(tentativas)
        conn = conectar()
        if conn is None:
            raise RuntimeError(
                f"Falha ao espelhar evento {event_id}; PostgreSQL indisponível para registrar o resultado."
            ) from exc
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.patrimonios_sheets_outbox
                       SET status = %s,
                           processando_em = NULL,
                           ultimo_erro = %s,
                           atualizado_em = now(),
                           proxima_tentativa_em = CASE
                               WHEN %s = 'failed' THEN now() + LEAST(
                                   interval '1 hour',
                                   interval '30 seconds' * power(2::double precision, GREATEST(0, tentativas)::double precision)
                               )
                               ELSE proxima_tentativa_em
                           END
                     WHERE id = %s AND status = 'processing'
                    """,
                    (status, str(exc)[:1000], status, event_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        raise RuntimeError(
            f"Evento {event_id} falhou e ficou em {status}; nenhum sucesso foi declarado."
        ) from exc

    conn = conectar()
    if conn is None:
        raise RuntimeError(
            f"Sheets foi relido com sucesso para o evento {event_id}, mas PostgreSQL está indisponível para confirmar o outbox."
        )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.patrimonios_sheets_outbox
                   SET status = 'synced',
                       processando_em = NULL,
                       ultimo_erro = NULL,
                       sincronizado_em = now(),
                       atualizado_em = now()
                 WHERE id = %s AND status = 'processing'
                RETURNING id
                """,
                (event_id,),
            )
            updated = cur.fetchone()
            if updated is None:
                raise RuntimeError(
                    f"Evento {event_id} deixou de estar processing; confirmação bloqueada."
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "event_id": event_id,
        "patrimonio_id": patrimonio_id,
        "status": "synced",
        "tentativas": tentativas,
        "readback_confirmado": True,
        "fila_fotos_processada": False,
        "outros_eventos_processados": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-id", type=int, required=True, help="ID exato em patrimonios_sheets_outbox")
    parser.add_argument("--execute", action="store_true", help="Executa a escrita; omitido significa somente leitura")
    parser.add_argument("--confirm-write", action="store_true", help="Confirma explicitamente a escrita no Google Sheets")
    args = parser.parse_args(argv)
    if args.event_id <= 0:
        parser.error("--event-id precisa ser um inteiro positivo.")
    try:
        validar_modo(args.execute, args.confirm_write)
        result = executar_evento_unico(args.event_id) if args.execute else inspecionar_evento(args.event_id)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if not args.execute:
            print("MODO SOMENTE LEITURA: nenhuma escrita foi realizada.", file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"ERRO: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
