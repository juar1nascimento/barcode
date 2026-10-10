-- Roles used by Supabase authorization may not exist in vanilla PostgreSQL CI.
DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN;
  END IF;
END
$roles$;

-- Supplemental fixtures layered on the repository's canonical PostgreSQL schema.
-- The base public.unidades, public.setores, and public.patrimonios tables must
-- come from postgresql_schema.sql; ativo must come from its versioned migration.
ALTER TABLE public.patrimonios
  ADD COLUMN IF NOT EXISTS tipo_custom text;

CREATE TABLE public.patrimonio_contagem_sessoes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  unidade_id bigint NOT NULL REFERENCES public.unidades(id),
  status text NOT NULL DEFAULT 'ativa',
  inicio_em timestamptz NOT NULL DEFAULT now(),
  nome text NOT NULL
);

CREATE TABLE public.patrimonio_contagem_metas (
  id bigserial PRIMARY KEY,
  unidade_id bigint NOT NULL REFERENCES public.unidades(id),
  ativo boolean NOT NULL DEFAULT true,
  tipo text NOT NULL,
  tipo_custom text,
  fabricante text,
  quantidade_total integer
);

CREATE TABLE public.patrimonio_contagem_eventos (
  id bigserial PRIMARY KEY,
  sessao_id uuid NOT NULL REFERENCES public.patrimonio_contagem_sessoes(id),
  meta_id bigint REFERENCES public.patrimonio_contagem_metas(id),
  patrimonio_id bigint REFERENCES public.patrimonios(id),
  codigo_barras text NOT NULL,
  origem text NOT NULL,
  resultado text NOT NULL,
  usuario text
);

INSERT INTO public.unidades (id, nome, tipo, ativo)
VALUES (2, 'Unidade de Teste GTI', 'UBS', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.setores (id, unidade_id, nome)
VALUES (2, 2, 'Setor de Teste')
ON CONFLICT (id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('public.unidades', 'id'),
              greatest((SELECT max(id) FROM public.unidades), 1));
SELECT setval(pg_get_serial_sequence('public.setores', 'id'),
              greatest((SELECT max(id) FROM public.setores), 1));
