-- GTI-SESA / Migração das fotos para a própria tabela patrimonios
-- As fotos passam a ficar na última coluna da tabela patrimonios, em sequência.
-- A migração preserva as fotos existentes antes de remover a tabela exclusiva.

ALTER TABLE patrimonios
    ADD COLUMN IF NOT EXISTS fotos JSONB NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF to_regclass('public.patrimonio_fotos') IS NOT NULL THEN
        UPDATE patrimonios p
           SET fotos = src.fotos,
               atualizado_em = NOW()
          FROM (
                SELECT patrimonio_id,
                       jsonb_agg(
                           jsonb_build_object(
                               'nome', sha256,
                               'arquivo_nome', sha256 || '.jpg',
                               'mime_type', mime_type,
                               'tamanho_bytes', tamanho_bytes,
                               'largura', largura,
                               'altura', altura,
                               'sha256', sha256,
                               'imagem_base64', encode(imagem, 'base64'),
                               'criado_em', criado_em
                           ) ORDER BY criado_em, id
                       ) AS fotos
                  FROM patrimonio_fotos
                 GROUP BY patrimonio_id
               ) src
         WHERE p.id = src.patrimonio_id;

        DROP TABLE patrimonio_fotos;
    END IF;
END $$;

ALTER TABLE patrimonios
    ALTER COLUMN fotos SET DEFAULT '[]'::jsonb;
