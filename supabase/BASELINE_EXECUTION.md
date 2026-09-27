# GTI-SESA — Execução do baseline Supabase

## Objetivo

Capturar o schema já existente no projeto Supabase como a primeira migration oficial, sem recriar tabelas, migrar dados ou executar `db push`.

Projeto: `vgabxdprocwmpmhoxrgt`

## Pré-requisitos

- Supabase CLI instalado.
- Acesso autenticado ao projeto.
- String de conexão PostgreSQL disponível, se o ambiente não usar o vínculo padrão.
- Executar em uma branch de desenvolvimento.

## Procedimento

```bash
supabase init
supabase link --project-ref vgabxdprocwmpmhoxrgt
supabase db pull
```

No primeiro `db pull`, aceitar o registro do baseline como já aplicado quando o CLI solicitar.

O resultado esperado é:

```
supabase/
  config.toml
  migrations/
    <timestamp>_remote_schema.sql
  verify_schema.sql
```

## Antes de qualquer push

Revisar o arquivo gerado e confirmar:

1. As tabelas `public.unidades`, `public.setores`, `public.patrimonios` e `public.patrimonio_fotos` estão presentes.
2. FKs, índices e constraints correspondem ao schema remoto auditado.
3. Não existem comandos destinados a apagar ou recriar dados históricos.
4. RLS e políticas existentes correspondem ao estado remoto.
5. O bucket/objetos do Storage não são tratados como dados a serem recriados pelo baseline.
6. O histórico passa a mostrar o baseline como aplicado.

Validar:

```bash
supabase migration list
```

## Validação local

Depois da revisão do baseline:

```bash
supabase db reset
```

O reset é somente local. **Não executar `supabase db reset --linked` neste projeto.**

## Estado conhecido antes do pull

- Schema remoto: íntegro.
- Dados auditados: 2 unidades, 3 setores, 3 patrimônios e 2 fotos.
- Órfãos de patrimônio/fotos: 0.
- Inconsistências unidade/setor: 0.
- Histórico remoto de migrations: vazio.
- RLS: habilitado nas quatro tabelas, sem políticas.
- Índices não utilizados: 3 avisos informativos.

## Próxima etapa após o pull

Comparar o migration baseline gerado com `postgresql_schema.sql` e com `supabase/verify_schema.sql`. Só depois dessa revisão será autorizada qualquer nova migration estrutural.
