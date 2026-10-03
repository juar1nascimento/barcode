-- GTI-SESA / Sistema de Inventários
-- Schema canônico de referência para PostgreSQL/Supabase.
-- Não executa migração de dados históricos.

CREATE TABLE IF NOT EXISTS public.unidades (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL UNIQUE,
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('UBS', 'URS', 'ALMOX')),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.setores (
    id BIGSERIAL PRIMARY KEY,
    unidade_id BIGINT NOT NULL REFERENCES public.unidades(id) ON DELETE CASCADE,
    nome VARCHAR(120) NOT NULL,
    numero_consultorio INTEGER,
    especialidade VARCHAR(150),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_setor_consultorio_numero CHECK (
        numero_consultorio IS NULL OR numero_consultorio > 0
    ),
    CONSTRAINT ck_setor_consultorio_dados CHECK (
        (nome = 'Consultório' AND numero_consultorio IS NOT NULL AND especialidade IS NOT NULL)
        OR
        (nome <> 'Consultório' AND numero_consultorio IS NULL AND especialidade IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_setor_normal
    ON public.setores (unidade_id, nome)
    WHERE nome <> 'Consultório' AND numero_consultorio IS NULL AND especialidade IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_setor_consultorio
    ON public.setores (unidade_id, numero_consultorio, especialidade)
    WHERE nome = 'Consultório'
      AND numero_consultorio IS NOT NULL
      AND especialidade IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.patrimonios (
    id BIGSERIAL PRIMARY KEY,
    unidade_id BIGINT NOT NULL REFERENCES public.unidades(id) ON DELETE RESTRICT,
    setor_id BIGINT NOT NULL REFERENCES public.setores(id) ON DELETE RESTRICT,
    tipo VARCHAR(50) NOT NULL CHECK (
        tipo IN ('CPU', 'Monitores', 'Teclado', 'Mouse', 'Imprenssoras', 'Outros Dispositivos')
    ),
    numero_patrimonio VARCHAR(150) NOT NULL,
    codigo_barras VARCHAR(150),
    fabricante VARCHAR(150),
    data_cadastro TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_patrimonio_numero UNIQUE (numero_patrimonio),
    CONSTRAINT uq_patrimonio_codigo_barras UNIQUE (codigo_barras)
);

CREATE INDEX IF NOT EXISTS idx_setores_unidade ON public.setores(unidade_id);
CREATE INDEX IF NOT EXISTS idx_patrimonios_unidade ON public.patrimonios(unidade_id);
CREATE INDEX IF NOT EXISTS idx_patrimonios_setor ON public.patrimonios(setor_id);
CREATE INDEX IF NOT EXISTS idx_patrimonios_tipo ON public.patrimonios(tipo);

CREATE TABLE IF NOT EXISTS public.patrimonio_fotos (
    id BIGSERIAL PRIMARY KEY,
    patrimonio_id BIGINT NOT NULL REFERENCES public.patrimonios(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL CHECK (ordem > 0),
    storage_bucket VARCHAR(100) NOT NULL DEFAULT 'patrimonio-fotos',
    storage_path VARCHAR(500) NOT NULL,
    arquivo_nome VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    tamanho_bytes INTEGER NOT NULL CHECK (tamanho_bytes > 0),
    largura INTEGER,
    altura INTEGER,
    sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-fA-F]{64}$'),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_patrimonio_fotos_dimensoes CHECK (
        (largura IS NULL AND altura IS NULL)
        OR (largura > 0 AND altura > 0)
    ),
    CONSTRAINT uq_patrimonio_fotos_ordem UNIQUE (patrimonio_id, ordem),
    CONSTRAINT uq_patrimonio_fotos_storage_path UNIQUE (storage_bucket, storage_path)
);

CREATE INDEX IF NOT EXISTS idx_patrimonio_fotos_patrimonio
    ON public.patrimonio_fotos(patrimonio_id);

CREATE INDEX IF NOT EXISTS idx_patrimonio_fotos_sha256
    ON public.patrimonio_fotos(sha256);

-- A coluna Setor do Google Sheets pode apresentar "Consultório 5 - Odontologia",
-- enquanto o PostgreSQL mantém nome, número e especialidade estruturados.
