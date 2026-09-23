-- GTI-SESA / Migração PostgreSQL - suporte ao Almoxarifado Central SESA
-- Idempotente: atualiza bancos existentes sem recriar a tabela.
-- Execute antes de cadastrar patrimônios da unidade ALMOX.

DO $$
BEGIN
    IF to_regclass('public.unidades') IS NULL THEN
        RAISE NOTICE 'Tabela public.unidades ainda não existe; aplique primeiro postgresql_schema.sql.';
        RETURN;
    END IF;

    -- Remove somente a constraint de tipo da tabela unidades.
    -- A nova regra é recriada abaixo.
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.unidades'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%tipo%'
    ) THEN
        EXECUTE (
            SELECT format('ALTER TABLE public.unidades DROP CONSTRAINT %I', conname)
            FROM pg_constraint
            WHERE conrelid = 'public.unidades'::regclass
              AND contype = 'c'
              AND pg_get_constraintdef(oid) ILIKE '%tipo%'
            ORDER BY conname
            LIMIT 1
        );
    END IF;

    ALTER TABLE public.unidades
        ADD CONSTRAINT ck_unidades_tipo
        CHECK (tipo IN ('UBS', 'URS', 'ALMOX'));

    RAISE NOTICE 'Constraint de tipo atualizada para UBS/URS/ALMOX.';
END
$$;