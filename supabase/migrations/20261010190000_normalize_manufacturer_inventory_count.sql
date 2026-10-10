-- GTI SESA
-- Corrige a associação de patrimônio à meta ignorando diferenças de caixa
-- e espaços externos no fabricante, priorizando correspondência exata.
-- ATENÇÃO: migration preparada para revisão; não executar em produção antes
-- de revisar, testar em ambiente apropriado e versionar na branch de correção.

CREATE OR REPLACE FUNCTION public.registrar_contagem_patrimonio(
    p_codigo text,
    p_origem text DEFAULT 'barcode'::text,
    p_unidade_id bigint DEFAULT 2,
    p_usuario text DEFAULT NULL::text
)
RETURNS TABLE(
    evento_id bigint,
    sessao_id uuid,
    patrimonio_id bigint,
    meta_id bigint,
    resultado text,
    quantidade_total integer,
    quantidade_conferida integer,
    quantidade_restante integer
)
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_codigo text := nullif(trim(p_codigo), '');
    v_origem text := lower(trim(p_origem));
    v_patrimonio public.patrimonios%rowtype;
    v_unidade_id bigint;
    v_sessao_id uuid;
    v_meta_id bigint;
    v_evento_id bigint;
    v_total integer;
    v_conferidos integer;
    v_restante integer;
BEGIN
    IF v_codigo IS NULL THEN
        RAISE EXCEPTION 'Código do patrimônio não informado';
    END IF;

    IF v_origem NOT IN ('barcode', 'manual') THEN
        RAISE EXCEPTION 'Origem inválida: use barcode ou manual';
    END IF;

    SELECT *
      INTO v_patrimonio
    FROM public.patrimonios p
    WHERE p.codigo_barras = v_codigo
       OR p.numero_patrimonio = v_codigo
    ORDER BY CASE WHEN p.codigo_barras = v_codigo THEN 0 ELSE 1 END
    LIMIT 1;

    IF v_patrimonio.id IS NOT NULL THEN
        v_unidade_id := v_patrimonio.unidade_id;
    ELSE
        v_unidade_id := coalesce(p_unidade_id, 2);
    END IF;

    PERFORM pg_advisory_xact_lock(v_unidade_id);

    SELECT s.id
      INTO v_sessao_id
    FROM public.patrimonio_contagem_sessoes s
    WHERE s.unidade_id = v_unidade_id
      AND s.status = 'ativa'
    ORDER BY s.inicio_em DESC
    LIMIT 1;

    IF v_sessao_id IS NULL THEN
        INSERT INTO public.patrimonio_contagem_sessoes (unidade_id, nome)
        VALUES (v_unidade_id, 'Contagem operacional')
        RETURNING id INTO v_sessao_id;
    END IF;

    IF v_patrimonio.id IS NULL THEN
        INSERT INTO public.patrimonio_contagem_eventos
            (sessao_id, patrimonio_id, codigo_barras, origem, resultado, usuario)
        VALUES
            (v_sessao_id, NULL, v_codigo, v_origem, 'nao_encontrado', p_usuario)
        RETURNING id INTO v_evento_id;

        RETURN QUERY
        SELECT v_evento_id, v_sessao_id, NULL::bigint, NULL::bigint,
               'nao_encontrado'::text, NULL::integer, 0::integer, NULL::integer;
        RETURN;
    END IF;

    IF NOT v_patrimonio.ativo THEN
        INSERT INTO public.patrimonio_contagem_eventos
            (sessao_id, patrimonio_id, codigo_barras, origem, resultado, usuario)
        VALUES
            (v_sessao_id, v_patrimonio.id, v_codigo, v_origem, 'invalido', p_usuario)
        RETURNING id INTO v_evento_id;

        RETURN QUERY
        SELECT v_evento_id, v_sessao_id, v_patrimonio.id, NULL::bigint,
               'invalido'::text, NULL::integer, 0::integer, NULL::integer;
        RETURN;
    END IF;

    IF v_unidade_id = 2 THEN
        SELECT m.id
          INTO v_meta_id
        FROM public.patrimonio_contagem_metas m
        WHERE m.unidade_id = 2
          AND m.ativo
          AND m.tipo = v_patrimonio.tipo
          AND (m.tipo_custom IS NULL
               OR m.tipo_custom IS NOT DISTINCT FROM v_patrimonio.tipo_custom)
          AND (
              m.fabricante IS NULL
              OR lower(trim(m.fabricante)) =
                 lower(trim(v_patrimonio.fabricante))
          )
        ORDER BY
            (m.fabricante = v_patrimonio.fabricante) IS TRUE DESC,
            (m.fabricante IS NOT NULL) DESC,
            (m.tipo_custom IS NOT NULL) DESC,
            m.id
        LIMIT 1;
    END IF;

    INSERT INTO public.patrimonio_contagem_eventos
        (sessao_id, meta_id, patrimonio_id, codigo_barras, origem, resultado, usuario)
    VALUES
        (v_sessao_id, v_meta_id, v_patrimonio.id, v_codigo, v_origem, 'encontrado', p_usuario)
    RETURNING id INTO v_evento_id;

    IF v_meta_id IS NOT NULL THEN
        SELECT m.quantidade_total
          INTO v_total
        FROM public.patrimonio_contagem_metas m
        WHERE m.id = v_meta_id;

        SELECT count(DISTINCT e.patrimonio_id)::integer
          INTO v_conferidos
        FROM public.patrimonio_contagem_eventos e
        WHERE e.meta_id = v_meta_id
          AND e.resultado = 'encontrado'
          AND e.patrimonio_id IS NOT NULL;

        v_restante := CASE
            WHEN v_total IS NULL THEN NULL
            ELSE greatest(v_total - v_conferidos, 0)
        END;
    ELSE
        v_total := NULL;
        v_conferidos := 0;
        v_restante := NULL;
    END IF;

    RETURN QUERY
    SELECT v_evento_id, v_sessao_id, v_patrimonio.id, v_meta_id,
           'encontrado'::text, v_total, v_conferidos, v_restante;
END;
$function$;
