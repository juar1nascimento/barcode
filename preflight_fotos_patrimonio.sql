-- GTI-SESA / Pré-auditoria da migração de fotos
-- SOMENTE LEITURA. Não altera nem remove dados.

SELECT
    to_regclass('public.patrimonios') AS tabela_patrimonios,
    to_regclass('public.patrimonio_fotos') AS tabela_patrimonio_fotos;

SELECT
    column_name,
    data_type,
    column_default,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'patrimonios'
  AND column_name = 'fotos';

SELECT
    COUNT(*) AS total_patrimonios,
    COUNT(*) FILTER (WHERE COALESCE(jsonb_array_length(fotos), 0) > 0) AS patrimonios_com_fotos,
    COALESCE(SUM(jsonb_array_length(fotos)), 0) AS total_fotos_jsonb
FROM patrimonios;

DO $$
BEGIN
    IF to_regclass('public.patrimonio_fotos') IS NOT NULL THEN
        RAISE NOTICE 'patrimonio_fotos: %, bytes de imagem: %',
            (SELECT COUNT(*) FROM patrimonio_fotos),
            (SELECT COALESCE(SUM(octet_length(imagem)), 0) FROM patrimonio_fotos);
    ELSE
        RAISE NOTICE 'patrimonio_fotos: tabela inexistente';
    END IF;
END $$;

SELECT
    p.id,
    p.numero_patrimonio,
    jsonb_array_length(COALESCE(p.fotos, '[]'::jsonb)) AS quantidade_fotos
FROM patrimonios p
WHERE jsonb_array_length(COALESCE(p.fotos, '[]'::jsonb)) > 0
ORDER BY p.id
LIMIT 50;
