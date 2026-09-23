-- GTI-SESA / Migração da foto do patrimônio
-- Executar uma vez no PostgreSQL/Supabase já existente.
ALTER TABLE patrimonios
    ADD COLUMN IF NOT EXISTS foto BYTEA;
