"""PostgreSQL integration tests for concurrent and expired outbox claims.

These tests run only against the disposable CI PostgreSQL service. They never
use application credentials or a configured production/Supabase connection.
"""

from concurrent.futures import ThreadPoolExecutor
import os

import psycopg
import pytest

import sincronizador_google_sheets as sincronizador
import inventario_sheets_outbox_worker as worker


DSN = os.getenv("TEST_POSTGRES_DSN")


@pytest.mark.skipif(not DSN, reason="TEST_POSTGRES_DSN não configurado")
def test_expired_lease_attempt_limit_and_concurrent_claims(monkeypatch):
    monkeypatch.setattr(sincronizador, "conectar", lambda: psycopg.connect(DSN))

    with psycopg.connect(DSN) as conn:
        conn.execute("DROP TABLE IF EXISTS public.patrimonios_sheets_outbox")
        conn.execute(
            """
            CREATE TABLE public.patrimonios_sheets_outbox (
                id BIGSERIAL PRIMARY KEY,
                patrimonio_id BIGINT NOT NULL,
                status TEXT NOT NULL,
                proxima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT now(),
                tentativas INTEGER NOT NULL DEFAULT 0,
                processando_em TIMESTAMPTZ,
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
                ultimo_erro TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO public.patrimonios_sheets_outbox
                (patrimonio_id, status, tentativas, processando_em)
            VALUES
                (101, 'processing', %s, now() - interval '20 minutes')
            """,
            (sincronizador.MAX_TENTATIVAS - 1,),
        )

    try:
        # Two independent consumers race for the same expired lease. SKIP LOCKED
        # plus the atomic UPDATE must allow exactly one consumer to claim it.
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    sincronizador._claim,
                    "patrimonios_sheets_outbox",
                    1,
                )
                for _ in range(2)
            ]
            results = [future.result(timeout=10) for future in futures]

        claimed = [item for batch in results for item in batch]
        assert len(claimed) == 1
        assert claimed[0]["patrimonio_id"] == 101
        assert claimed[0]["tentativas"] == sincronizador.MAX_TENTATIVAS

        # Once that final attempt's lease expires, the event must become
        # dead_letter instead of being reclaimed indefinitely.
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """
                UPDATE public.patrimonios_sheets_outbox
                   SET processando_em=now() - interval '20 minutes'
                 WHERE id=%s
                """,
                (claimed[0]["id"],),
            )

        assert sincronizador._claim("patrimonios_sheets_outbox", 1) == []

        with psycopg.connect(DSN) as conn:
            row = conn.execute(
                """
                SELECT status, tentativas, processando_em, ultimo_erro
                  FROM public.patrimonios_sheets_outbox
                 WHERE id=%s
                """,
                (claimed[0]["id"],),
            ).fetchone()

        assert row[0] == "dead_letter"
        assert row[1] == sincronizador.MAX_TENTATIVAS
        assert row[2] is None
        assert "limite de tentativas" in row[3]
    finally:
        with psycopg.connect(DSN) as conn:
            conn.execute("DROP TABLE IF EXISTS public.patrimonios_sheets_outbox")



@pytest.mark.skipif(not DSN, reason="TEST_POSTGRES_DSN não configurado")
def test_primary_worker_enforces_attempt_limit_for_claim_and_stale_reset():
    with psycopg.connect(DSN) as conn:
        conn.execute("DROP TABLE IF EXISTS public.patrimonios_sheets_outbox")
        conn.execute(
            """
            CREATE TABLE public.patrimonios_sheets_outbox (
                id BIGSERIAL PRIMARY KEY,
                patrimonio_id BIGINT NOT NULL,
                status TEXT NOT NULL,
                proxima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT now(),
                tentativas INTEGER NOT NULL DEFAULT 0,
                processando_em TIMESTAMPTZ,
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
                ultimo_erro TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO public.patrimonios_sheets_outbox
                (patrimonio_id, status, tentativas, processando_em)
            VALUES
                (201, 'processing', %s, now() - interval '20 minutes'),
                (202, 'failed', %s, now()),
                (203, 'failed', %s, now())
            """,
            (
                worker_max := 8,
                worker_max - 1,
                worker_max,
            ),
        )

    try:
        with psycopg.connect(DSN) as conn:
            worker.reset_stale(conn, worker_max)

        with psycopg.connect(DSN) as conn:
            exhausted = conn.execute(
                """
                SELECT status, processando_em, ultimo_erro
                  FROM public.patrimonios_sheets_outbox
                 WHERE patrimonio_id=201
                """
            ).fetchone()
            assert exhausted[0] == "dead_letter"
            assert exhausted[1] is None
            assert "limite de tentativas" in exhausted[2]

            claimed = worker.claim_batch(conn, 10, worker_max)
            assert len(claimed) == 1
            assert claimed[0][1] == 202

            state = conn.execute(
                """
                SELECT status, tentativas
                  FROM public.patrimonios_sheets_outbox
                 WHERE patrimonio_id=202
                """
            ).fetchone()
            assert state == ("processing", worker_max)

            excluded = conn.execute(
                """
                SELECT status, tentativas
                  FROM public.patrimonios_sheets_outbox
                 WHERE patrimonio_id=203
                """
            ).fetchone()
            assert excluded == ("failed", worker_max)
    finally:
        with psycopg.connect(DSN) as conn:
            conn.execute("DROP TABLE IF EXISTS public.patrimonios_sheets_outbox")
