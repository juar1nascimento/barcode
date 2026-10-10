-- Assertions exercise the actual migration function on the canonical base schema.
INSERT INTO public.patrimonio_contagem_metas
  (id, unidade_id, ativo, tipo, tipo_custom, fabricante, quantidade_total)
VALUES
  (101, 2, true, 'CPU', NULL, 'HP', 3),
  (102, 2, true, 'CPU', NULL, 'Hp', 4),
  (103, 2, true, 'Monitores', NULL, 'HP', 2);

INSERT INTO public.patrimonios
  (unidade_id, setor_id, tipo, numero_patrimonio, codigo_barras, fabricante, ativo, tipo_custom)
VALUES
  (2, 2, 'CPU', 'P-EXACT', 'ASSET-EXACT', 'HP', true, NULL),
  (2, 2, 'Monitores', 'P-NORMALIZED', 'ASSET-NORMALIZED', ' hP ', true, NULL),
  (2, 2, 'CPU', 'P-AMBIGUOUS', 'ASSET-AMBIGUOUS', 'hP', true, NULL),
  (2, 2, 'Monitores', 'P-INACTIVE', 'ASSET-INACTIVE', 'HP', false, NULL);

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

  RAISE NOTICE 'PASS: canonical schema + exact, normalized, ambiguous, missing, inactive cases';
END
$test$;
