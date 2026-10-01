-- GTI-SESA: add logical active flag for inventory records.
-- Keeps photos and movement history while removing excluded records from the
-- operational inventory view.

ALTER TABLE public.patrimonios
  ADD COLUMN IF NOT EXISTS ativo boolean NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS idx_patrimonios_unidade_ativo
  ON public.patrimonios (unidade_id, ativo);

UPDATE public.patrimonios
   SET ativo = true
 WHERE ativo IS NULL;
