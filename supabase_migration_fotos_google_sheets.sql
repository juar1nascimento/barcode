-- GTI-SESA: fotos visíveis no Google Sheets
-- A planilha usa =IMAGE(URL), portanto o objeto precisa estar acessível por URL.
-- O arquivo continua sendo o original armazenado no bucket do Supabase.
UPDATE storage.buckets
SET public = true
WHERE id = 'patrimonio-fotos';


-- Reconciliação operacional e limites de retry ficam em migrations versionadas do Supabase.


-- GTI-SESA: reconciliação automática da fila de fotos com Google Sheets
-- Recria eventos de sincronização ausentes sem duplicar eventos existentes.

CREATE OR REPLACE FUNCTION public.reconcile_patrimonio_fotos_sheets_outbox(p_limit integer DEFAULT 500)
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
    SELECT pf.id AS foto_id, pf.patrimonio_id
      FROM public.patrimonio_fotos pf
     WHERE NOT EXISTS (
       SELECT 1
         FROM public.patrimonio_fotos_sheets_outbox o
        WHERE o.foto_id = pf.id
          AND o.evento = 'upsert'
     )
     ORDER BY pf.id
     LIMIT p_limit
  )
  INSERT INTO public.patrimonio_fotos_sheets_outbox
      (patrimonio_id, foto_id, evento, status, proxima_tentativa_em)
  SELECT patrimonio_id, foto_id, 'upsert', 'pending', now()
    FROM candidatos
  ON CONFLICT (foto_id, evento) WHERE foto_id IS NOT NULL DO NOTHING;

  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION public.reconcile_patrimonio_fotos_sheets_outbox(integer) FROM PUBLIC, anon, authenticated;

CREATE INDEX IF NOT EXISTS ix_fotos_sheets_outbox_patrimonio_id
ON public.patrimonio_fotos_sheets_outbox (patrimonio_id);
