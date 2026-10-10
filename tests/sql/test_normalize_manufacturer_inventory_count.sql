-- Assertions exercise the actual migration function against isolated fixtures.
INSERT INTO public.patrimonio_contagem_metas
  (id, unidade_id, ativo, tipo, tipo_custom, fabricante, quantidade_total)
VALUES
  (101, 2, true, 'computador', NULL, 'HP', 3),
  (102, 2, true, 'computador', NULL, 'Hp', 4),
  (103, 2, true, 'impressora', NULL, 'HP', 2);

INSERT INTO public.patrimonios
  (codigo_barras, numero_patrimonio, unidade_id, ativo, tipo, tipo_custom, fabricante)
VALUES
  ('ASSET-EXACT', 'P-EXACT', 2, true, 'computador', NULL, 'HP'),
  ('ASSET-NORMALIZED', 'P-NORMALIZED', 2, true, 'impressora', NULL, ' hP '),
  ('ASSET-AMBIGUOUS', 'P-AMBIGUOUS', 2, true, 'computador', NULL, 'hP'),
  ('ASSET-INACTIVE', 'P-INACTIVE', 2, false, 'impressora', NULL, 'HP');

DO $test$
DECLARE
  r record;
BEGIN
  SELECT * INTO r FROM public.registrar_contagem_patrimonio('ASSET-EXACT');
  IF r.meta_id IS DISTINCT FROM 101 OR r.resultado <> 'encontrado' THEN
    RAISE EXCEPTION 'Exact manufacturer match failed: %', row_to_json(r);
  END IF;

  SELECT * INTO r FROM public.registrar_contagem_patrimonio('ASSET-NORMALIZED');
  IF r.meta_id IS DISTINCT FROM 103 OR r.resultado <> 'encontrado' THEN
    RAISE EXCEPTION 'Case/trim normalized match failed: %', row_to_json(r);
  END IF;

  SELECT * INTO r FROM public.registrar_contagem_patrimonio('ASSET-AMBIGUOUS');
  IF r.meta_id IS NOT NULL OR r.resultado <> 'encontrado' THEN
    RAISE EXCEPTION 'Ambiguous manufacturer must not choose a meta: %', row_to_json(r);
  END IF;

  SELECT * INTO r FROM public.registrar_contagem_patrimonio('MISSING-ASSET');
  IF r.resultado <> 'nao_encontrado' OR r.patrimonio_id IS NOT NULL THEN
    RAISE EXCEPTION 'Missing asset behavior regressed: %', row_to_json(r);
  END IF;

  SELECT * INTO r FROM public.registrar_contagem_patrimonio('ASSET-INACTIVE');
  IF r.resultado <> 'invalido' THEN
    RAISE EXCEPTION 'Inactive asset behavior regressed: %', row_to_json(r);
  END IF;

  RAISE NOTICE 'PASS: exact, normalized, ambiguous, missing, inactive cases';
END
$test$;
