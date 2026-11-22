# GTI SESA — Gate 10B: reconciliação da origem dos SQLs de Outbox

- **Estado:** investigação Git read-only; inconclusiva para as migrations originais de Drive/local.
- **Data:** 2026-11-22.
- **Base de análise:** branches, árvores Git, arquivos e commits acessíveis no repositório.
- **Sem acesso operacional:** esta rodada não consultou Supabase remoto nem executou SQL.

## 1. Resultado executivo

A busca ampliada encontrou artefatos próximos, mas não recuperou os SQLs originais específicos das funções de claim/finalize/fail do Drive Outbox nem a migration de lease da Outbox local. Dois falsos positivos potenciais foram identificados e descartados por diferença de escopo:

1. `20261013130000_gti_drive_folder_lease.sql` controla exclusão mútua na criação/verificação de pastas Drive por patrimônio. Não implementa lease de eventos em `patrimonio_fotos_drive_outbox`.
2. `20261001154000_harden_trigger_function_execute_privileges.sql` revoga/granta EXECUTE de `validar_movimentacao_patrimonio()`. Não é o SQL correspondente ao registro remoto `20261001184053_harden_trigger_function_execute_privileges`, cujo contexto registrado é hardening das funções Outbox SECURITY DEFINER.

Não renomear, copiar ou declarar esses arquivos como equivalentes aos SQLs pendentes.

## 2. Branches examinadas nesta rodada

A listagem GitHub de branches foi filtrada por nomes relacionados a outbox, lease, Drive, local, migration, photo e foto. Árvores recursivas foram examinadas, entre outras, nas branches:

- `fix/gti-drive-folder-lease-gate-20261013`
- `feat/local-drive-mirror-worker`
- `fix/gti-photo-outbox-reconciliation-20261025`
- `feat/sigs-inventory-photo-workflow-20261029`
- `feat/download-only-drive-photos-local`
- `feat/local-drive-api-download`
- `fix/gti-worker-drive-root-compat-20261013`
- `chore/gti-outbox-triggers-prod-migration-20261012`
- `audit/postgresql-fotos-preflight`
- `fix/fotos-patrimonio-definitivo`
- `fix/fotos-google-sheets`

Nas árvores verificadas, não foram encontrados os caminhos exatos:
- `20261003230654_add_safe_drive_outbox_claim.sql`
- `20261003235815_harden_drive_outbox_finalize_idempotent.sql`
- `20261003235928_harden_drive_outbox_retry_dead_letter.sql`
- `20261007213327_add_local_photo_worker_leases.sql`
- `20261001184053_harden_trigger_function_execute_privileges.sql`

A busca de commits por nome exato das cinco migrations também não retornou resultados. Busca por texto em commits não é índice exaustivo de conteúdo Git; ausência de resultado não prova inexistência em todo histórico, refs apagadas, forks ou backups.

## 3. Artefatos encontrados e classificação

### 3.1 Lease de pasta Drive — não é lease da Outbox

Na branch `fix/gti-drive-folder-lease-gate-20261013`, foi localizado:
- arquivo: `supabase/migrations/20261013130000_gti_drive_folder_lease.sql`
- blob: `5da4996770c7513331ee246ea55fc2b18aff3345`

O SQL cria `gti_drive_folder_leases`, com PK `patrimonio_id`, `lease_token` e `lease_until`, e funções `gti_acquire_drive_folder_lease` / `gti_release_drive_folder_lease`. O objetivo explícito é serializar criação/verificação de pastas por patrimônio. O contrato não reivindica linhas da tabela `patrimonio_fotos_drive_outbox`, não altera status de evento e não substitui claim/finalize/fail da Outbox. Não usar como migration de fencing de evento.

### 3.2 Hardening de trigger — migration de escopo diferente

Na mesma branch foi encontrado:
- arquivo: `supabase/migrations/20261001154000_harden_trigger_function_execute_privileges.sql`
- blob: `51cfa22b01c65964f6f300ff5fd1a72c7a283e37`

Seu conteúdo trata exclusivamente de `public.validar_movimentacao_patrimonio()`. O histórico remoto previamente consultado registra versão `20261001184053_harden_trigger_function_execute_privileges` associada ao hardening das funções Outbox. Os nomes são semelhantes, mas timestamp e objeto SQL diferem. Não há evidência suficiente de equivalência ou de que o arquivo encontrado seja a origem da migration remota.

### 3.3 Worker Drive legado

O commit `d5782dac5fabc36cf40926d2d7d452a43de0300b` adicionou worker incremental Drive. A leitura do diff confirma:
- claim em SQL direto, com `FOR UPDATE SKIP LOCKED`;
- pending com teto de tentativas;
- ramo processing antigo sem teto;
- tentativa não incrementada ao recuperar processing expirado;
- atualização final da Outbox por ID, sem token;
- efeitos externos no Drive entre claim e finalização.

O commit `9fcefe5a94e99b3329907e00b67f26d2847b7312` acrescenta failed ao ramo de claim, mas não corrige os demais pontos citados. Estes são achados do código daquele commit; não provam isoladamente o conteúdo de todo artefato atualmente implantado.

### 3.4 Worker REST local

O commit `78ef0a30c0959a573d87c40c72c912060f6b13f9` adicionou `workers/local_drive_mirror_worker.py`. O código recuperado:
- lê a fila via REST;
- reivindica com PATCH condicionado a `status=pending`;
- incrementa tentativas no claim;
- não usa `lease_token` nem `lease_expires_at`;
- não recupera `processing` expirado no caminho examinado;
- usa transições intermediárias `drive_delete_pending` e `completed`.

Isso não substitui o SQL remoto de claim/complete/fail da fila local e não prova que seja a única implementação existente.

## 4. SQLs originais: estado de recuperação

| Versão registrada | Resultado desta rodada |
|---|---|
| `20261003230654_add_safe_drive_outbox_claim` | Não recuperada |
| `20261003235815_harden_drive_outbox_finalize_idempotent` | Não recuperada |
| `20261003235928_harden_drive_outbox_retry_dead_letter` | Não recuperada |
| `20261007213327_add_local_photo_worker_leases` | Não recuperada |
| `20261001184053_harden_trigger_function_execute_privileges` | Não recuperada; arquivo semelhante encontrado tem timestamp/objeto diferentes |

As quatro primeiras continuam pendentes. A quinta não pode ser satisfeita pelo arquivo de hardening de trigger localizado.

## 5. Próximas fontes de recuperação permitidas

Antes de qualquer reconstrução, procurar:
1. checkout local do proprietário, incluindo `.git/objects`, refs locais/remotas, reflogs e branches não publicadas;
2. backups de repositório e bundles Git;
3. histórico de PRs/commits que contenham os arquivos originais ou patches;
4. artefatos de CI/versionamento que tenham preservado o SQL original;
5. registro de migration e histórico de release, apenas para correlação, sem executar migrations.

Se o proprietário disponibilizar o checkout local, executar buscas read-only e preservar cópia dos objetos encontrados. Não pedir nem imprimir credenciais.

## 6. Decisão técnica

Não criar migration substituta nesta etapa. Não gerar SQL novo a partir de `pg_get_functiondef`, não renomear migrations com timestamp divergente, não alterar `schema_migrations`, não editar funções instaladas e não assumir equivalência com base em nome semelhante.

Se os arquivos originais não puderem ser recuperados após esgotar fontes Git/backups disponíveis, a alternativa será uma migration nova, aditiva e explicitamente versionada, baseada em especificação aprovada e estado de catálogo novamente confirmado. Essa proposta deverá incluir compatibilidade com todos os consumidores e plano de cutover/rollback.

## 7. Limites

Esta rodada usou somente leitura do GitHub. Nenhuma conexão Supabase foi aberta; nenhum SELECT, DDL, DML ou função SQL foi executado; nenhum worker, workflow operacional, Google Sheets, Drive ou filesystem local foi acessado. Nenhuma alteração em main, merge ou deploy ocorreu.
