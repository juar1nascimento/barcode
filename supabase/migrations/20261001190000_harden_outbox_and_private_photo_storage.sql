-- GTI-SESA: close remaining public exposure in integration outbox and photo storage.
-- Operational backend uses the private PostgreSQL connection/service role only.
-- No anon/authenticated policy is intentionally created for these tables.

ALTER TABLE public.patrimonios_sheets_outbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.patrimonios_sheets_outbox FROM anon, authenticated, public;

REVOKE ALL ON TABLE public.patrimonio_fotos_sheets_outbox FROM anon, authenticated, public;

UPDATE storage.buckets
   SET public = false
 WHERE id = 'patrimonio-fotos';
