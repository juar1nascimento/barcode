-- GTI-SESA / Validação não destrutiva do schema Supabase
-- Este arquivo SOMENTE consulta metadados. Não executa DDL nem altera dados.
-- Projeto esperado: vgabxdprocwmpmhoxrgt
--
-- Objetivo: validar o estado remoto antes e depois do baseline/migrations.

SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relkind,
    c.relrowsecurity AS rls_enabled
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('unidades', 'setores', 'patrimonios', 'patrimonio_fotos')
ORDER BY c.relname;

SELECT
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('unidades', 'setores', 'patrimonios', 'patrimonio_fotos')
ORDER BY table_name, ordinal_position;

SELECT
    conrelid::regclass AS table_name,
    conname AS constraint_name,
    contype,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid IN (
    'public.unidades'::regclass,
    'public.setores'::regclass,
    'public.patrimonios'::regclass,
    'public.patrimonio_fotos'::regclass
)
ORDER BY conrelid::regclass::text, conname;

SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('unidades', 'setores', 'patrimonios', 'patrimonio_fotos')
ORDER BY tablename, indexname;

SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('unidades', 'setores', 'patrimonios', 'patrimonio_fotos')
ORDER BY tablename, policyname;

SELECT
    (SELECT count(*) FROM public.unidades) AS unidades,
    (SELECT count(*) FROM public.setores) AS setores,
    (SELECT count(*) FROM public.patrimonios) AS patrimonios,
    (SELECT count(*) FROM public.patrimonio_fotos) AS fotos,
    (SELECT count(*)
       FROM public.patrimonios p
       LEFT JOIN public.setores s ON s.id = p.setor_id
      WHERE s.id IS NULL) AS patrimonios_setor_orfaos,
    (SELECT count(*)
       FROM public.patrimonios p
       LEFT JOIN public.unidades u ON u.id = p.unidade_id
      WHERE u.id IS NULL) AS patrimonios_unidade_orfaos,
    (SELECT count(*)
       FROM public.patrimonio_fotos f
       LEFT JOIN public.patrimonios p ON p.id = f.patrimonio_id
      WHERE p.id IS NULL) AS fotos_orfas,
    (SELECT count(*)
       FROM public.patrimonios p
       JOIN public.setores s ON s.id = p.setor_id
      WHERE p.unidade_id <> s.unidade_id) AS patrimonio_unidade_setor_inconsistente,
    (SELECT count(*)
       FROM public.patrimonios
      WHERE tipo NOT IN (
          'CPU', 'Monitores', 'Teclado', 'Mouse',
          'Imprenssoras', 'Outros Dispositivos'
      )) AS tipos_invalidos;
