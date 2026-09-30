-- GTI-SESA: fila durável de sincronização dos patrimônios com Google Sheets.
-- O registro principal continua em public.patrimonios. Esta fila apenas
-- garante que uma falha temporária do Google Sheets possa ser recuperada.

CREATE TABLE IF NOT EXISTS public.patrimonios_sheets_outbox (
    id BIGSERIAL PRIMARY KEY,
    patrimonio_id BIGINT NOT NULL REFERENCES public.patrimonios(id) ON DELETE CASCADE,
    evento TEXT NOT NULL DEFAULT 'upsert',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','processing','failed','synced','dead_letter')),
    tentativas INTEGER NOT NULL DEFAULT 0 CHECK (tentativas >= 0),
    proxima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    processando_em TIMESTAMPTZ,
    sincronizado_em TIMESTAMPTZ,
    ultimo_erro TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (patrimonio_id, evento)
);

CREATE INDEX IF NOT EXISTS ix_patrimonios_sheets_outbox_pendente
ON public.patrimonios_sheets_outbox (status, proxima_tentativa_em, id);

CREATE INDEX IF NOT EXISTS ix_patrimonios_sheets_outbox_patrimonio
ON public.patrimonios_sheets_outbox (patrimonio_id);

CREATE OR REPLACE FUNCTION public.reconcile_patrimonios_sheets_outbox(p_limit integer DEFAULT 500)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_count integer;
BEGIN
    IF p_limit IS NULL OR p_limit < 1 THEN
        RAISE EXCEPTION 'p_limit deve ser maior que zero';
    END IF;

    WITH candidatos AS (
        SELECT p.id AS patrimonio_id
          FROM public.patrimonios p
         WHERE NOT EXISTS (
             SELECT 1
               FROM public.patrimonios_sheets_outbox o
              WHERE o.patrimonio_id = p.id
                AND o.evento = 'upsert'
         )
         ORDER BY p.id
         LIMIT p_limit
    )
    INSERT INTO public.patrimonios_sheets_outbox
        (patrimonio_id, evento, status, proxima_tentativa_em)
    SELECT patrimonio_id, 'upsert', 'pending', now()
      FROM candidatos
    ON CONFLICT (patrimonio_id, evento) DO NOTHING;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION public.reconcile_patrimonios_sheets_outbox(integer)
FROM PUBLIC, anon, authenticated;
