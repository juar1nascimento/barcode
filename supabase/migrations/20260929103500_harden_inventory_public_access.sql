-- GTI-SESA: harden inventory tables for the private backend architecture.
-- The Streamlit application uses a private PostgreSQL connection and does not
-- use the Supabase Data API for these tables.

REVOKE ALL ON TABLE
  public.unidades,
  public.setores,
  public.patrimonios,
  public.patrimonio_fotos,
  public.movimentacoes_patrimonio
FROM anon, authenticated, public;

DROP POLICY IF EXISTS "deny_anon_authenticated_unless_backend" ON public.unidades;
CREATE POLICY "deny_anon_authenticated_unless_backend"
ON public.unidades AS RESTRICTIVE
FOR ALL TO anon, authenticated
USING (false)
WITH CHECK (false);

DROP POLICY IF EXISTS "deny_anon_authenticated_unless_backend" ON public.setores;
CREATE POLICY "deny_anon_authenticated_unless_backend"
ON public.setores AS RESTRICTIVE
FOR ALL TO anon, authenticated
USING (false)
WITH CHECK (false);

DROP POLICY IF EXISTS "deny_anon_authenticated_unless_backend" ON public.patrimonios;
CREATE POLICY "deny_anon_authenticated_unless_backend"
ON public.patrimonios AS RESTRICTIVE
FOR ALL TO anon, authenticated
USING (false)
WITH CHECK (false);

DROP POLICY IF EXISTS "deny_anon_authenticated_unless_backend" ON public.patrimonio_fotos;
CREATE POLICY "deny_anon_authenticated_unless_backend"
ON public.patrimonio_fotos AS RESTRICTIVE
FOR ALL TO anon, authenticated
USING (false)
WITH CHECK (false);

DROP POLICY IF EXISTS "deny_anon_authenticated_unless_backend" ON public.movimentacoes_patrimonio;
CREATE POLICY "deny_anon_authenticated_unless_backend"
ON public.movimentacoes_patrimonio AS RESTRICTIVE
FOR ALL TO anon, authenticated
USING (false)
WITH CHECK (false);

CREATE INDEX IF NOT EXISTS idx_mov_setor_destino
  ON public.movimentacoes_patrimonio (setor_destino_id);

CREATE INDEX IF NOT EXISTS idx_mov_setor_origem
  ON public.movimentacoes_patrimonio (setor_origem_id);

CREATE INDEX IF NOT EXISTS idx_patrimonios_setor_unidade
  ON public.patrimonios (setor_id, unidade_id);
