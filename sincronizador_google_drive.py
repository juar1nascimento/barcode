"""Consumidor idempotente Supabase -> Google Drive para fotos patrimoniais."""

from __future__ import annotations

from psycopg import sql

from google_drive_fotos import sincronizar_foto_drive
from postgresql_persistencia import conectar

MAX_TENTATIVAS = 5
STALE_MINUTES = 15


def _claim(limit: int = 25) -> list[dict]:
    conn = conectar()
    if conn is None:
        raise RuntimeError("PostgreSQL indisponível.")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH candidatos AS (
                    SELECT id
                      FROM public.patrimonio_fotos_drive_outbox
                     WHERE (
                         status='pending'
                         AND proxima_tentativa_em <= now()
                         AND tentativas < %s
                     ) OR (
                         status='processing'
                         AND processando_em < now() - make_interval(mins => %s)
                     )
                     ORDER BY id
                     FOR UPDATE SKIP LOCKED
                     LIMIT %s
                )
                UPDATE public.patrimonio_fotos_drive_outbox o
                   SET status='processing',
                       processando_em=now(),
                       tentativas=CASE
                           WHEN o.status='processing' THEN o.tentativas
                           ELSE o.tentativas + 1
                       END,
                       atualizado_em=now()
                  FROM candidatos c
                 WHERE o.id=c.id
             RETURNING o.id,o.patrimonio_id,o.foto_id,o.tentativas
                """,
                (MAX_TENTATIVAS, STALE_MINUTES, max(1, min(int(limit), 100))),
            )
            rows = cur.fetchall()
        conn.commit()
        return [
            {
                "id": int(r[0]),
                "patrimonio_id": int(r[1]),
                "foto_id": int(r[2]),
                "tentativas": int(r[3]),
            }
            for r in rows
        ]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _buscar_foto(foto_id: int) -> dict:
    conn = conectar()
    if conn is None:
        raise RuntimeError("PostgreSQL indisponível.")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id,f.ordem,f.storage_bucket,f.storage_path,f.sha256,
                       p.numero_patrimonio,u.nome
                  FROM public.patrimonio_fotos f
                  JOIN public.patrimonios p ON p.id=f.patrimonio_id
                  JOIN public.unidades u ON u.id=p.unidade_id
                 WHERE f.id=%s
                """,
                (foto_id,),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("Foto não encontrada.")
        return {
            "id": int(row[0]),
            "ordem": int(row[1]),
            "bucket": str(row[2]),
            "path": str(row[3]),
            "sha256": str(row[4]).strip(),
            "numero": str(row[5]),
            "unidade": str(row[6]),
        }
    finally:
        conn.close()


def _marcar(evento_id: int, *, status: str, tentativas: int, erro: str | None = None, drive: dict | None = None) -> None:
    conn = conectar()
    if conn is None:
        raise RuntimeError("PostgreSQL indisponível.")
    try:
        with conn.cursor() as cur:
            if status == "synced" and drive:
                cur.execute(
                    """
                    UPDATE public.patrimonio_fotos_drive_outbox
                       SET status='synced',
                           processando_em=NULL,
                           sincronizado_em=now(),
                           ultimo_erro=NULL,
                           atualizado_em=now()
                     WHERE id=%s
                    """,
                    (evento_id,),
                )
                cur.execute(
                    """
                    UPDATE public.patrimonio_fotos
                       SET drive_file_id=%s,
                           drive_file_name=%s,
                           drive_folder_id=%s,
                           drive_web_url=%s,
                           drive_sha256=%s
                     WHERE id=%s
                    """,
                    (
                        drive["id"],
                        drive["name"],
                        drive["folder_id"],
                        drive["web_url"],
                        None,
                        _marcar.foto_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE public.patrimonio_fotos_drive_outbox
                       SET status=%s,
                           processando_em=NULL,
                           ultimo_erro=%s,
                           proxima_tentativa_em=CASE
                             WHEN %s='failed'
                             THEN now() + make_interval(secs => LEAST(3600, 30 * (2 ^ GREATEST(0, %s))))
                             ELSE proxima_tentativa_em
                           END,
                           atualizado_em=now()
                     WHERE id=%s
                    """,
                    (status, (erro or "")[:1000] or None, status, tentativas, evento_id),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def processar_fila_google_drive(limit: int = 25) -> dict:
    resultado = {"processados": 0, "sucesso": 0, "falhas": 0, "dead_letter": 0}
    for item in _claim(limit):
        resultado["processados"] += 1
        try:
            foto = _buscar_foto(item["foto_id"])
            drive = sincronizar_foto_drive(
                unidade=foto["unidade"],
                numero=foto["numero"],
                ordem=foto["ordem"],
                bucket=foto["bucket"],
                path=foto["path"],
                sha256=foto["sha256"],
            )
            # A atualização do metadata e a confirmação do outbox são feitas
            # na mesma transação, para que o Sheets só enxergue uma foto
            # oficialmente entregue quando o Drive já tiver confirmado o arquivo.
            conn = conectar()
            if conn is None:
                raise RuntimeError("PostgreSQL indisponível.")
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE public.patrimonio_fotos
                           SET drive_file_id=%s,
                               drive_file_name=%s,
                               drive_folder_id=%s,
                               drive_web_url=%s,
                               drive_sha256=%s
                         WHERE id=%s
                        """,
                        (
                            drive["id"], drive["name"], drive["folder_id"],
                            drive["web_url"], foto["sha256"], foto["id"],
                        ),
                    )
                    cur.execute(
                        """
                        UPDATE public.patrimonio_fotos_drive_outbox
                           SET status='synced',
                               processando_em=NULL,
                               sincronizado_em=now(),
                               ultimo_erro=NULL,
                               atualizado_em=now()
                         WHERE id=%s
                        """,
                        (item["id"],),
                    )
                conn.commit()
            finally:
                conn.close()
            resultado["sucesso"] += 1
        except Exception as exc:
            tentativas = item["tentativas"]
            status = "dead_letter" if tentativas >= MAX_TENTATIVAS else "failed"
            try:
                conn = conectar()
                if conn is not None:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE public.patrimonio_fotos_drive_outbox
                               SET status=%s,
                                   processando_em=NULL,
                                   ultimo_erro=%s,
                                   proxima_tentativa_em=CASE
                                     WHEN %s='failed'
                                     THEN now() + make_interval(secs => LEAST(3600, 30 * (2 ^ GREATEST(0, %s))))
                                     ELSE proxima_tentativa_em
                                   END,
                                   atualizado_em=now()
                             WHERE id=%s
                            """,
                            (
                                status,
                                str(exc)[:1000],
                                status,
                                tentativas,
                                item["id"],
                            ),
                        )
                    conn.commit()
                    conn.close()
            finally:
                pass
            resultado["falhas"] += 1
            if status == "dead_letter":
                resultado["dead_letter"] += 1
    return resultado
