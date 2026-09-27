# Plano de Baseline Não Destrutivo — GTI-SESA

## Objetivo

Sincronizar o histórico de migrations do repositório com o schema já existente no projeto Supabase sem recriar tabelas, sem alterar dados e sem reaplicar a migration legada.

## Estado confirmado

- Projeto Supabase: `vgabxdprocwmpmhoxrgt`.
- O banco publicado possui as tabelas `unidades`, `setores`, `patrimonios` e `patrimonio_fotos`.
- As estruturas, FKs, checks, índices e regras de unicidade auditadas estão coerentes com o código.
- A constraint de `unidades.tipo` já aceita `UBS`, `URS` e `ALMOX`.
- O histórico remoto de migrations consultado está vazio.
- `migrations/001_almoxarifado_tipo.sql` é uma alteração incremental legada e não representa o estado completo atual do banco.
- O checkpoint de integridade anterior ao baseline foi capturado em 2026-09-27T10:14:25.169447+00:00:
  - unidades: 2
  - setores: 3
  - patrimonios: 3
  - fotos: 2
  - registros órfãos/inconsistentes: 0
- A validação não destrutiva está versionada em `supabase/verify_schema.sql`.

## Estado desta etapa

**Baseline oficial ainda não capturado.**

O ambiente disponível para esta execução não expõe a Supabase CLI. As ferramentas disponíveis permitem consultar e alterar o banco, mas não fornecem o fluxo oficial `supabase db pull` necessário para gerar o arquivo de baseline e registrar corretamente a migration remota.

Por segurança, não será criado um baseline manualmente e não será usada uma migration inventada para preencher o histórico.

## Procedimento oficial pendente

Em um ambiente com a Supabase CLI instalada:

1. Verificar a CLI:
   `supabase --version`
2. Verificar os comandos disponíveis:
   `supabase --help`
   `supabase db pull --help`
3. Inicializar a estrutura local somente se necessário:
   `supabase init`
4. Vincular o projeto:
   `supabase link --project-ref vgabxdprocwmpmhoxrgt`
5. Capturar o estado remoto:
   `supabase db pull`
6. Revisar integralmente o SQL gerado em `supabase/migrations/*_remote_schema.sql`.
7. Confirmar que o arquivo representa o estado já existente e não introduz alterações indevidas.
8. Conferir o histórico:
   `supabase migration list`
9. Somente depois do baseline validado, criar migrations incrementais para mudanças novas.
10. Antes de qualquer aplicação futura, usar `supabase db push --dry-run` e revisar o resultado.

## Regras para a migration legada 001

Não executar `migrations/001_almoxarifado_tipo.sql` como baseline.

O banco atual já possui `unidades.tipo` compatível com `UBS`, `URS` e `ALMOX`. Portanto, aplicar essa migration agora seria uma alteração histórica desnecessária e poderia produzir divergência entre o estado real e a sequência de migrations.

A disposição definitiva desse arquivo deve ser tratada somente depois de o baseline oficial existir e de a cadeia histórica poder ser reconciliada com segurança.

## Próximo passo técnico

O próximo passo que realmente fecha a lacuna de sincronização é executar o `supabase db pull` oficial no ambiente que tenha a CLI e acesso ao projeto.

Até essa captura, **não executar `db push`, `apply_migration`, `migration repair` ou alterações DDL no banco** apenas para tentar fabricar o histórico.

## Critério de conclusão

A etapa será considerada concluída quando houver evidência de que:

- existe um arquivo de baseline gerado pelo `supabase db pull`;
- o SQL do baseline foi revisado;
- o estado remoto permaneceu íntegro;
- o histórico local/remoto está coerente;
- a migration 001 não foi reaplicada como baseline;
- a próxima mudança puder ser representada por uma migration incremental controlada.
