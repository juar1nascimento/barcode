-- GTI-SESA / Sistema de Inventários
-- Schema definitivo para PostgreSQL em nuvem (Supabase).
-- O Google Sheets permanece como tabela operacional/espelho.
-- Este arquivo cria apenas a estrutura; NÃO migra dados históricos.

CREATE TABLE IF NOT EXISTS unidades (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL UNIQUE,
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('UBS', 'URS', 'ALMOX')),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS setores (
    id BIGSERIAL PRIMARY KEY,
    unidade_id BIGINT NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
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

-- Regras de unicidade sem depender da semântica de NULL do PostgreSQL:
-- 1) setor normal: uma ocorrência por unidade/nome;
-- 2) consultório: uma ocorrência por unidade/número/especialidade.
CREATE UNIQUE INDEX IF NOT EXISTS uq_setor_normal
    ON setores (unidade_id, nome)
    WHERE nome <> 'Consultório' AND numero_consultorio IS NULL AND especialidade IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_setor_consultorio
    ON setores (unidade_id, numero_consultorio, especialidade)
    WHERE nome = 'Consultório' AND numero_consultorio IS NOT NULL AND especialidade IS NOT NULL;

CREATE TABLE IF NOT EXISTS patrimonios (
    id BIGSERIAL PRIMARY KEY,
    unidade_id BIGINT NOT NULL REFERENCES unidades(id) ON DELETE RESTRICT,
    setor_id BIGINT NOT NULL REFERENCES setores(id) ON DELETE RESTRICT,
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

CREATE INDEX IF NOT EXISTS idx_setores_unidade ON setores(unidade_id);
CREATE INDEX IF NOT EXISTS idx_patrimonios_unidade ON patrimonios(unidade_id);
CREATE INDEX IF NOT EXISTS idx_patrimonios_setor ON patrimonios(setor_id);
CREATE INDEX IF NOT EXISTS idx_patrimonios_tipo ON patrimonios(tipo);

-- Compatibilidade operacional: a coluna Setor do Google Sheets pode continuar
-- exibindo "Consultório 5 - Odontologia", enquanto o PostgreSQL mantém os
-- componentes estruturados em nome/numero_consultorio/especialidade.

CREATE TABLE IF NOT EXISTS patrimonio_fotos (
    id BIGSERIAL PRIMARY KEY,
    patrimonio_id BIGINT NOT NULL REFERENCES patrimonios(id) ON DELETE CASCADE,
    imagem BYTEA NOT NULL,
    mime_type VARCHAR(50) NOT NULL DEFAULT 'image/jpeg',
    tamanho_bytes INTEGER NOT NULL CHECK (tamanho_bytes > 0),
    largura INTEGER,
    altura INTEGER,
    sha256 CHAR(64) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_patrimonio_foto UNIQUE (patrimonio_id),
    CONSTRAINT ck_patrimonio_foto_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_patrimonio_fotos_patrimonio
    ON patrimonio_fotos(patrimonio_id);
