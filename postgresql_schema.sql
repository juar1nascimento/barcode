-- GTI-SESA / Sistema de Inventários
-- Schema relacional para armazenamento principal no PostgreSQL.
-- O Google Sheets permanece como tabela operacional/espelho.

CREATE TABLE IF NOT EXISTS unidades (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL UNIQUE,
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('UBS', 'URS')),
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
    CONSTRAINT uq_setor_unidade_descricao UNIQUE (
        unidade_id, nome, numero_consultorio, especialidade
    )
);

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
