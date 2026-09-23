-- GTI-SESA / Migração PostgreSQL - suporte ao Almoxarifado Central SESA
-- Idempotente: atualiza bancos existentes sem recriar a tabela.
-- Execute antes de cadastrar patrimônios da unidade ALMOX.

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    IF to_regclass('public.unidades') IS NULL THEN
        RAISE NOTICE 'Tabela public.unidades ainda não existe; aplique primeiro postgresql_schema.sql.';
        RETURN;
    END IF;

    -- Remove a constraint gerenciada por esta migração, caso já exista.
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.unidades'::regclass
          AND conname = 'ck_unidades_tipo'
    ) THEN
        ALTER TABLE public.unidades DROP CONSTRAINT ck_unidades_tipo;
    END IF;

    -- Remove constraints legadas que restringem a coluna tipo.
    -- A busca exige referências aos tipos antigos para evitar remover checks
    -- não relacionados à classificação da unidade.
    FOR constraint_name IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'public.unidades'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%tipo%'
          AND pg_get_constraintdef(oid) ILIKE '%UBS%'
          AND pg_get_constraintdef(oid) ILIKE '%URS%'
    LOOP
        EXECUTE format(
            'ALTER TABLE public.unidades DROP CONSTRAINT %I',
            constraint_name
        );
    END LOOP;

    ALTER TABLE public.unidades
        ADD CONSTRAINT ck_unidades_tipo
        CHECK (tipo IN ('UBS', 'URS', 'ALMOX'));

    RAISE NOTICE 'Constraint de tipo atualizada para UBS/URS/ALMOX.';
END
$$;
