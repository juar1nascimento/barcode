-- Harden movement semantics without changing existing rows.
ALTER TABLE public.movimentacoes_patrimonio
  ADD CONSTRAINT ck_mov_entrada_destino
  CHECK (tipo <> 'ENTRADA' OR (unidade_destino_id IS NOT NULL AND setor_destino_id IS NOT NULL)),
  ADD CONSTRAINT ck_mov_saida_origem
  CHECK (tipo <> 'SAIDA' OR unidade_origem_id IS NOT NULL),
  ADD CONSTRAINT ck_mov_transferencia_completa
  CHECK (tipo <> 'TRANSFERENCIA' OR (unidade_origem_id IS NOT NULL AND setor_origem_id IS NOT NULL AND unidade_destino_id IS NOT NULL AND setor_destino_id IS NOT NULL));
