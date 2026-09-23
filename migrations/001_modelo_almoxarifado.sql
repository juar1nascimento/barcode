-- ETAPA 4: migração estrutural segura do modelo PostgreSQL.
-- NÃO executar automaticamente no banco de produção.
-- Pré-requisito: conferir dados existentes antes de aplicar.

BEGIN;

ALTER TABLE unidades
    ALTER COLUMN tipo TYPE VARCHAR(20);

ALTER TABLE unidades
    DROP CONSTRAINT IF EXISTS unidades_tipo_check;

ALTER TABLE unidades
    ADD CONSTRAINT unidades_tipo_check
    CHECK (tipo IN ('UBS', 'URS', 'ALMOXARIFADO'));

COMMIT;
