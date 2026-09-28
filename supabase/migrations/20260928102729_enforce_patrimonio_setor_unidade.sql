-- Enforce that a patrimonio belongs to the same unidade as its setor.
-- Existing data was verified before applying this migration.

ALTER TABLE public.setores
  ADD CONSTRAINT uq_setor_id_unidade UNIQUE (id, unidade_id);

ALTER TABLE public.patrimonios
  ADD CONSTRAINT fk_patrimonio_setor_unidade
  FOREIGN KEY (setor_id, unidade_id)
  REFERENCES public.setores (id, unidade_id)
  ON DELETE RESTRICT;
