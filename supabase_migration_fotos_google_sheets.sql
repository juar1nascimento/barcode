-- GTI-SESA: fotos visíveis no Google Sheets
-- A planilha usa =IMAGE(URL), portanto o objeto precisa estar acessível por URL.
-- O arquivo continua sendo o original armazenado no bucket do Supabase.
UPDATE storage.buckets
SET public = true
WHERE id = 'patrimonio-fotos';


-- Reconciliação operacional e limites de retry ficam em migrations versionadas do Supabase.
