-- GTI-SESA / Migração 001 - Fotos no Supabase Storage
-- SOMENTE PROPOSTA DE MIGRAÇÃO.
-- NÃO executar em produção sem backup, revisão e validação das policies.
--
-- Objetivo:
--   1) permitir ALMOX como tipo de unidade;
--   2) manter patrimônios sem BYTEA/Base64;
--   3) criar relação patrimonios -> patrimonio_fotos;
--   4) guardar no PostgreSQL apenas metadados/referência do Storage.
--
-- O bucket do Storage NÃO é criado por este arquivo.
-- Criá-lo separadamente no Supabase Dashboard como:
--   patrimonio-fotos
--
-- Esta migration NÃO migra dados históricos e NÃO remove a coluna fotos.
-- A remoção da coluna fotos será uma etapa posterior, depois da validação
-- da aplicação e de eventual migração de dados legados.

BEGIN;

-- 1. Habilitar ALMOX no domínio de unidades existente.
ALTER TABLE public.unidades
    DROP CONSTRAINT IF EXISTS unidades_tipo_check;

ALTER TABLE public.unidades
    ADD CONSTRAINT unidades_tipo_check
    CHECK (tipo IN ('UBS', 'URS', 'ALMOX));

-- 2. Tabela relacional das fotos.
CREATE TABLE IF NOT EXISTS public.patrimonio_fotos (
    id BIGSERIAL PRIMARY KEY,
    patrimonio_id BIGINT NOT NULL
        REFERENCES public.patrimonios(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL,
    storage_bucket VARCHAR(100) NOT NULL DEFAULT 'patrimonio-fotos',
    storage_path VARCHAR(500) NOT NULL,
    arquivo_nome VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    tamanho_bytes INTEGER NOT NULL,
    largura INTEGER,
    altura INTEGER,
    sha256 CHAR(64) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_patrimonio_fotos_ordem CHECK (ordem > 0),
    CONSTRAINT ck_patrimonio_fotos_tamanho CHECK (tamanho_bytes > 0),
    CONSTRAINT ck_patrimonio_fotos_dimensoes CHECK (
        (largura IS NULL AND altura IS NULL)
        OR (largura > 0 AND altura > 0)
    ),
    CONSTRAINT ck_patrimonio_fotos_sha256 CHECK (sha256 ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT uq_patrimonio_fotos_ordem UNIQUE (patrimonio_id, ordem),
    CONSTRAINT uq_patrimonio_fotos_storage_path UNIQUE (storage_bucket, storage_path)
);

CREATE INDEX IF NOT EXISTS idx_patrimonio_fotos_patrimonio
    ON public.patrimonio_fotos(patrimonio_id);

CREATE INDEX IF NOT EXISTS idx_patrimonio_fotos_sha256
    ON public.patrimonio_fotos(sha256);

-- 3. RLS da nova tabela.
ALTER TABLE public.patrimonio_fotos ENABLE ROW LEVEL SECURITY;

-- 4. Políticas deliberadamente NÃO criadas nesta primeira migration.
-- Elas dependem do modelo de autenticação efetivamente usado pela aplicação.
-- Depois da auditoria do login/roles, criaremos SELECT/INSERT/UPDATE/DELETE
-- mínimos e específicos.

COMMIT;
