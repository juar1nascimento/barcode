# Auditoria de Preparação do Baseline — Etapa 11

## Resultado

A preparação foi revisada contra a documentação atual do Supabase.

### Achados

1. O repositório não possui atualmente `supabase/config.toml`.
2. A migration legada está em `migrations/001_almoxarifado_tipo.sql`, fora de `supabase/migrations/`.
3. Portanto, ainda não existe uma estrutura local oficial do Supabase CLI neste branch.
4. O banco remoto já possui o schema funcional auditado e o histórico de migrations consultado está vazio.

## Decisão segura

Não criar manualmente um arquivo de migration com timestamp e não mover a migration 001 neste momento.

A documentação oficial atual indica que, para um projeto remoto existente, o fluxo de baseline é inicializar/validar o projeto local, vincular o projeto remoto e executar `supabase db pull --linked`. O `db pull` gera a migration de baseline a partir do schema remoto e oferece registrar essa migration como aplicada no histórico remoto sem executar novamente o SQL. citeturn0search1turn0search2

## Próxima ação operacional

A próxima etapa deve ser executada em um ambiente que possua a Supabase CLI:

1. `supabase --version`
2. `supabase init` apenas se não houver estrutura local.
3. `supabase link --project-ref vgabxdprocwmpmhoxrgt`
4. `supabase db pull --linked`
5. revisar o SQL gerado antes de qualquer outra ação.

**Não executar `supabase db push`, `supabase db reset --linked` ou qualquer SQL de alteração remota.** O `db reset --linked` é explicitamente destrutivo. citeturn0search1

## Critério de parada

Depois do `db pull`, a execução deve parar para revisão se o SQL gerado contiver qualquer objeto inesperado, `DROP`, alteração de RLS/policies, grants/revokes inesperados ou divergência em relação ao schema auditado.

Somente após essa revisão poderá ser considerada a sincronização do histórico de migrations.
