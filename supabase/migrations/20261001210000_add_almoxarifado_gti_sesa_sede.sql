-- Unidade adicional do Sistema de Inventários GTI-SESA
-- Mantém a mesma estrutura operacional do Almoxarifado Central SESA.

INSERT INTO public.unidades (nome, tipo, ativo)
VALUES ('Almoxarifado GTI-SESA-SEDE', 'ALMOX', TRUE)
ON CONFLICT (nome) DO UPDATE
SET tipo = EXCLUDED.tipo,
    ativo = TRUE;

INSERT INTO public.setores (unidade_id, nome, ativo)
SELECT u.id, v.nome, TRUE
FROM public.unidades u
CROSS JOIN (VALUES ('Almoxarifado'), ('Odontologia')) AS v(nome)
WHERE u.nome = 'Almoxarifado GTI-SESA-SEDE'
ON CONFLICT (unidade_id, nome)
WHERE (nome <> 'Consultório' AND numero_consultorio IS NULL AND especialidade IS NULL)
DO UPDATE SET ativo = TRUE;
