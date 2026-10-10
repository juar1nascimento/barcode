-- Isolated PostgreSQL fixtures for the manufacturer-normalization migration.
-- This schema is intentionally minimal and disposable; it is not production schema.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE public.patrimonios (
  id bigserial PRIMARY KEY,
  codigo_barras text,
  numero_patrimonio text,
  unidade_id bigint NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  tipo text NOT NULL,
  tipo_custom text,
  fabricante text
);

CREATE TABLE public.patrimonio_contagem_sessoes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  unidade_id bigint NOT NULL,
  status text NOT NULL DEFAULT 'ativa',
  inicio_em timestamptz NOT NULL DEFAULT now(),
  nome text NOT NULL
);

CREATE TABLE public.patrimonio_contagem_metas (
  id bigserial PRIMARY KEY,
  unidade_id bigint NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  tipo text NOT NULL,
  tipo_custom text,
  fabricante text,
  quantidade_total integer
);

CREATE TABLE public.patrimonio_contagem_eventos (
  id bigserial PRIMARY KEY,
  sessao_id uuid NOT NULL,
  meta_id bigint,
  patrimonio_id bigint,
  codigo_barras text NOT NULL,
  origem text NOT NULL,
  resultado text NOT NULL,
  usuario text
);
