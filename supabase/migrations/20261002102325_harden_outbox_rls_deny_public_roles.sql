-- Defense-in-depth: the Outbox tables are backend-only.
-- Keep RLS enabled and explicitly deny Data API roles.
-- The worker uses the privileged backend role and is unaffected.
CREATE POLICY "deny_anon_authenticated_unless_backend"
ON public.patrimonio_fotos_sheets_outbox
AS RESTRICTIVE
FOR ALL
TO anon, authenticated
USING (false)
WITH CHECK (false);

CREATE POLICY "deny_anon_authenticated_unless_backend"
ON public.patrimonios_sheets_outbox
AS RESTRICTIVE
FOR ALL
TO anon, authenticated
USING (false)
WITH CHECK (false);
