-- GTI-SESA / Migração idempotente do armazenamento de fotos
-- Execute no banco PostgreSQL já existente antes de usar a câmera do Almoxarifado.

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
