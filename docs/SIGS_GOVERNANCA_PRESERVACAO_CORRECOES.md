# SIGS — Registro de Governança, Auditoria e Preservação de Correções

- **Data do registro:** 2026-11-22
- **Sistema:** Inventário GTI-SESA
- **Repositório:** `juar1nascimento/barcode`
- **Responsável pelas autorizações:** proprietário do sistema
- **Estado deste registro:** documentação de desenvolvimento; não representa publicação em produção.

## 1. Objetivo

Manter rastreabilidade das movimentações recentes, resultados de testes, correções e riscos conhecidos. A rotina diária deve detectar regressões sem apagar, substituir ou reverter correções anteriores.

Este documento segue o princípio da ADR-001: a outbox persistida é a fonte durável dos eventos, polling permanece como fallback até validação isolada, e nenhuma integração externa deve ser ativada apenas por publicação de código.

## 2. Movimentações recentes

### 2.1 PR #90 — segurança de dependências e validação de integração

- Branch: `fix/security-dependencies-codeql-20261115`.
- Commit de correção: `6100d4d9c248ea947cd729ee1aaadab64d48e680`.
- Correção: atualização de `tornado` de `6.6` para `6.6.1`, mitigando a vulnerabilidade identificada no scanner.
- A branch foi sincronizada localmente pelo proprietário por fast-forward, sem rebase, force push ou alteração de `main`.
- PR #90: https://github.com/juar1nascimento/barcode/pull/90.
- Estado registrado: draft, aberto e sem merge.

### 2.2 Testes da PR #90

Na execução associada ao commit `6100d4d`, os cinco workflows foram aprovados:

1. GTI SESA — Event wake-up contract.
2. Testes Python.
3. System Audit.
4. Inventário GTI SESA — CI.
5. Inventário GTI SESA — Security.

Evidências registradas:
- 155 testes Python aprovados.
- `pip-audit` sem vulnerabilidades conhecidas encontradas na execução.
- Compilação Python, auditoria estática, inicialização do Streamlit e CodeQL aprovados.

A validação foi de CI. Não equivale a teste operacional contra PostgreSQL/Supabase, Google Sheets ou Drive.

### 2.3 PR #91 — recuperação de eventos failed da Outbox

- Branch: `fix/outbox-failed-retry-20261122`.
- Commit head registrado: `37be568ddbc0cd47996f339058b02b04e2200f12`.
- PR #91: https://github.com/juar1nascimento/barcode/pull/91.
- Base: `fix/security-dependencies-codeql-20261115`.
- Estado no momento da abertura deste registro: draft, aberto e sem merge.
- Arquivos: `sincronizador_google_sheets.py` e `tests/test_sincronizador_google_sheets_claim.py`.

**Defeito identificado:** o consumidor alternativo marcava eventos como `failed`, mas a consulta de reivindicação não os selecionava novamente após o backoff. Isso podia deixar falhas permanentemente paradas nesse consumidor.

**Correção proposta:** incluir `failed` na seleção elegível, respeitando `proxima_tentativa_em <= now()` e `tentativas < MAX_TENTATIVAS`, mantendo `FOR UPDATE SKIP LOCKED` e o tratamento já existente de `processing` expirado.

**Testes adicionados:** verificam o contrato SQL de seleção, limite de tentativas, backoff, `SKIP LOCKED` e rejeição de nome de tabela inválido.

**CI — resultado final observado em 2026-11-22:** Testes Python aprovado com **157 testes passados** (1 warning de compatibilidade emitido por dependência); Security aprovado com Source hardening, Dependency review e CodeQL concluídos com sucesso. A PR não foi mesclada.

## 3. Riscos técnicos ainda abertos

Os itens abaixo permanecem pendentes e não devem ser considerados corrigidos pelas PRs #90 ou #91:

1. `reset_stale()` do worker principal recupera `processing` após 15 minutos sem heartbeat/renovação de lease; operação longa pode permitir reivindicação concorrente.
2. O consumidor alternativo recupera `processing` expirado sem incrementar tentativas, podendo contornar o limite.
3. Não há cobertura suficiente de testes para `claim`, `reset_stale`, `mark`, concorrência, dead-letter, movimentação e baixa.
4. Movimentações e desativações de patrimônio não inserem, de forma comprovada, evento correspondente na outbox na mesma transação.
5. A reconciliação atual não detecta todas as atualizações posteriores nem eventos de movimentação/baixa.
6. Workers e writers diretos para Google Sheets coexistem; é necessário consolidar um caminho único de escrita e prevenir concorrência/duplicidade.
7. Os workflows operacionais podem ter grupos de concorrência diferentes e executar em paralelo.
8. A modelagem de eventos deve decidir formalmente entre log append-only e fila coalescida antes de qualquer alteração de schema.

## 4. Política de preservação de correções

A rotina de auditoria diária deve operar em modo de preservação:

- Ler e registrar o estado de branches, commits, PRs, reviews e checks antes de recomendar mudanças.
- Tratar commits aprovados, correções em PR e alterações locais ainda não conciliadas como conteúdo protegido contra descarte.
- Nunca executar reset, revert, rebase destrutivo, force push, exclusão de branch, substituição de arquivo ou atualização automática de dependências.
- Nunca atualizar `main`, mesclar PR, publicar, disparar sincronização operacional ou executar migration automaticamente.
- Detectar divergência entre branch local e remota; recomendar reconciliação por fast-forward quando aplicável, sem executar comandos locais em nome do proprietário.
- Se encontrar regressão, investigar causa raiz. Para bug determinístico, inequívoco, de baixo risco, reversível e restrito ao código da aplicação, pode preparar correção em branch isolada, adicionar teste de regressão, executar testes relevantes e abrir PR draft para revisão do proprietário. Para qualquer mudança de alto risco ou que afete dados, integrações, autenticação/autorização, permissões, contratos, arquitetura ou operação, apresentar evidências, impacto, proposta e rollback e aguardar autorização específica.
- Se o estado de CI estiver em andamento ou indisponível, registrar exatamente esse estado; não inferir sucesso.
- Não registrar segredos, tokens, IDs privados de planilhas ou valores de credenciais.

### Selo nas configurações

A interface administrativa SIGS passa a exibir o indicador:

**🛡️ PRESERVAÇÃO DE CORREÇÕES — POLÍTICA ATIVA**

O selo é informativo e visível somente ao administrador autenticado. Não é um mecanismo de proteção de branch do GitHub nem substitui permissões, checks obrigatórios, revisão ou autorização humana. Não há botão para desativá-lo nesta etapa.

## 5. Rotina diária das 08:00

A automação denominada **Auditoria diária GTI SESA** está cadastrada com recorrência diária às 08:00, fuso `America/Sao_Paulo`, porém foi encontrada desabilitada/pausada em 2026-11-22. Portanto, não afirmar que está executando até ser reativada pelo proprietário.

Quando habilitada, deve:
1. Consultar PRs, branches, commits, diffs, reviews, checks e logs, diferenciando sucesso, falha, execução em andamento, ausência de execução e integração externa não testada.
2. Detectar anomalias funcionais, regressões, erros, vulnerabilidades, divergências de configuração e riscos de perda de dados; registrar evidências, severidade, impacto e causa raiz ou hipótese.
3. Para correções pequenas, inequívocas, reversíveis e restritas ao código da aplicação, preparar alteração em branch isolada, criar teste de regressão, executar testes relevantes e abrir PR draft para revisão do proprietário.
4. Para cada achado material, preparar adendo SIGS datado e append-only em branch isolada/PR draft; nunca substituir registros anteriores nem escrever diretamente em `main`.
5. Não fazer merge, deploy, migration, alteração de schema, escrita operacional em Supabase/PostgreSQL, Google Sheets ou Drive, edição de patrimônios, alteração de credenciais, permissões ou workflows operacionais.
6. Não modificar `main`, reescrever histórico, descartar correções, alterar dependências automaticamente ou modificar PRs existentes de forma destrutiva.
7. Quando o risco for alto, a causa não for inequívoca ou houver impacto em dados, integrações, segurança, contratos, arquitetura ou operação, parar na análise e aguardar autorização específica do proprietário.
8. Informar alterações propostas/realizadas, arquivos, diffs, testes e resultados, links de PR e bloqueios; se não houver novidade material, declarar isso explicitamente.

**Estado atualizado em 2026-11-22:** as instruções da auditoria foram ampliadas para detecção e correção controlada, e a automação foi reativada após a validação dessas salvaguardas. A recorrência permanece diária, com alvo aproximado às 08:00 em `America/Sao_Paulo` (horário flexível, não garantia de execução exatamente às 08:00).

## 6. Gates seguintes

- **Gate A:** concluir CI da PR #91 e revisar os logs/testes; não mesclar.
- **Gate B:** sincronizar a branch de governança com a branch local somente por fast-forward, após CI aprovado.
- **Gate C:** testar a renderização e autorização da tela de Configurações SIGS em ambiente local, sem produção.
- **Gate D:** desenhar testes de lease/heartbeat e recuperação de falhas nos dois consumidores.
- **Gate E:** definir formalmente o modelo de eventos de movimentação/baixa antes de qualquer migration.
- **Gate F:** consolidar os writers Sheets e revisar os workflows concorrentes.

## 7. Limites de execução

Nenhuma migration, escrita no Supabase/PostgreSQL, escrita no Google Sheets/Drive, sincronização operacional, deploy ou merge foi executado como parte deste registro. A integração em produção permanece bloqueada até autorização expressa do proprietário e conclusão dos gates pertinentes.


## 8. Adendo de auditoria — PR #93 e integridade dos leases (2026-11-22)

### 8.1 Consulta documental e escopo

Este adendo foi preparado após consulta deste registro SIGS e da ADR-001. A ADR-001 mantém a outbox persistida como fila durável, exige reivindicação atômica/idempotente e preserva o polling como mecanismo de reconciliação. O presente trabalho limita-se ao controle de tentativas dos consumidores existentes; não ativa notificações, workers ou integrações externas.

### 8.2 PR #93 — limite de tentativas em leases expirados

- PR: https://github.com/juar1nascimento/barcode/pull/93
- Branch: `fix/outbox-expired-lease-limit-20261122`.
- Base: `fix/outbox-failed-retry-20261122` (PR #91).
- Head auditado: `8261d9a514c50fac01b144c28adf0c2769565ba8`.
- Estado consultado: aberta, draft, mergeable; não mesclada.
- Escopo alterado: `sincronizador_google_sheets.py`, `inventario_sheets_outbox_worker.py`, testes de claim e integração PostgreSQL, e workflow de testes.
- A PR limita a reivindicação de eventos pending/failed e processing expirados pelo orçamento de tentativas; incrementa o contador em nova reivindicação; e move leases expirados já esgotados para `dead_letter`. O worker principal recebe o limite configurado em `OUTBOX_MAX_ATTEMPTS`; o consumidor alternativo aplica `MAX_TENTATIVAS`.
- Os dois caminhos preservam `FOR UPDATE SKIP LOCKED`. Não foi proposta migration nem alteração de schema.

### 8.3 Evidências de CI

Execuções associadas ao head acima, concluídas em 2026-11-22:

- **Testes Python:** sucesso; **159 testes passaram**, com 1 aviso de compatibilidade do plugin pytest/AnyIO.
- **Security:** sucesso em CodeQL, Source hardening e Dependency Review.
- O job de testes inicializou PostgreSQL 16 efêmero e executou os testes de integração contra esse serviço descartável.
- Não foram usadas credenciais do ambiente real, nem executados SELECT/INSERT/UPDATE em Supabase/PostgreSQL de produção, sincronização Sheets/Drive ou workflow operacional.

O resultado comprova os checks de CI para o commit indicado; não comprova comportamento operacional em produção.

### 8.4 Revisão e estado de aprovação

Na consulta realizada, a PR #93 não possuía reviews submetidos nem threads de revisão. Portanto, CI aprovado não equivale a aprovação humana nem autorização de merge. A PR permanece draft e deve continuar sem merge até revisão do proprietário e conclusão dos gates dependentes.

### 8.5 Atualização do quadro de riscos

- **Limite de tentativas após expiração:** correção proposta na PR #93 para os dois consumidores; considerada coberta pelos testes do CI, ainda pendente de integração/revisão.
- **Heartbeat/renovação de lease:** continua aberto. O timeout fixo de 15 minutos pode ainda permitir que um trabalho legítimo, de duração superior ao lease, seja considerado expirado. A PR #93 limita o número de reaquisições, mas não implementa heartbeat nem prova exclusão durante operações longas. Qualquer solução que exija coluna, token de lease ou migration deve ser objeto de desenho e autorização específica.
- **Movimentações/baixas, reconciliação incompleta, writers diretos e concorrência entre workflows:** permanecem riscos separados, não resolvidos pela PR #93.
- **Cobertura:** foram adicionados testes PostgreSQL descartáveis para concorrência/limite no consumidor alternativo e para reset/claim no worker principal. Isso não substitui a cobertura futura de heartbeat, baixa, movimentação, duplicidade de append e escritores paralelos.

### 8.6 Consistência documental entre PRs

A descrição atual da PR #92 ainda afirma que a automação diária permanece desabilitada. O texto deste documento, na seção 5, registra sua reativação e estado habilitado em 2026-11-22. A divergência é de metadado/descrição da PR #92; este adendo não altera a descrição nem o estado da automação. Corrigir a descrição da PR #92 em ação documental separada, preservando o histórico.

### 8.7 Próximo gate seguro

1. Manter PRs #90–#93 abertas em draft e sem merge até revisão ordenada das dependências.
2. Fazer revisão técnica independente do SQL CTE e dos dois consumidores da PR #93, incluindo semântica de tentativas e transições para dead-letter.
3. Tratar heartbeat/lease renewal primeiro como diagnóstico e desenho. Não alterar schema, criar migration ou tocar em banco real sem autorização específica.
4. Manter bloqueadas as validações operacionais com PostgreSQL/Supabase real, Google Sheets e Drive.

**Limites confirmados neste adendo:** nenhuma alteração em `main`, merge, deploy, migration, escrita em banco real, sincronização operacional ou alteração de credenciais foi realizada.


## 9. Adendo de auditoria — isolamento dos testes PostgreSQL (2026-11-22)

### 9.1 Achado na revisão independente da PR #93

Na revisão dos testes de integração PostgreSQL da PR #93, foi identificado que `tests/test_sincronizador_google_sheets_claim_postgres.py` executava `DROP TABLE IF EXISTS public.patrimonios_sheets_outbox` e `CREATE TABLE` sempre que `TEST_POSTGRES_DSN` estivesse configurado. O workflow fornece um serviço PostgreSQL efêmero, mas o próprio teste não verificava se a DSN apontava efetivamente para esse serviço.

**Risco:** configuração local ou de CI incorreta poderia direcionar operações destrutivas de teste a uma instância não descartável. O risco decorre da ausência de validação no próprio teste; não há evidência de que tenha ocorrido qualquer conexão ou exclusão em banco real.

### 9.2 PR #95 — guarda fail-closed para o banco de testes

- PR: https://github.com/juar1nascimento/barcode/pull/95
- Branch: `fix/test-postgres-disposable-guard-20261122`.
- Base: head da PR #93 (`8261d9a514c50fac01b144c28adf0c2769565ba8`).
- Head registrado: `2282049b4a018f0c6e674e20d39d70c10003c4f1`.
- Estado consultado: aberta, draft, sem merge.
- A alteração exige `GITHUB_ACTIONS=true`, host/hostaddr em loopback e banco/usuário esperados antes de qualquer conexão dos testes de integração.
- Foram adicionados testes unitários para rejeitar execução fora do GitHub Actions e DSN remoto.
- Escopo limitado ao arquivo de testes; não altera worker, aplicação, migration ou schema.

### 9.3 CI e validação pendente

Na consulta inicial ao commit da PR #95, os workflows **Testes Python** e **Inventário GTI SESA - Security** estavam em andamento. Portanto, nenhum resultado final foi presumido. Atualizar este registro somente após consultar as execuções vinculadas ao head exato.

### 9.4 Gate de segurança

Até a aprovação do CI da PR #95:
1. Não considerar o harness PostgreSQL da PR #93 isolado por completo.
2. Manter PRs #93 e #95 em draft e sem merge.
3. Confirmar que os testes de guarda falham sem `GITHUB_ACTIONS=true` e para DSN não local.
4. Confirmar que os testes de integração continuam executando contra o serviço efêmero do workflow.
5. Não executar esses testes com DSN de Supabase, produção ou qualquer banco persistente.

**Limites confirmados:** nenhum teste foi direcionado a banco real; nenhuma escrita, exclusão, migration, sincronização externa, merge ou deploy foi executado durante esta revisão.

## 10. Adendo de auditoria — reconciliação do histórico de migrations e catálogo Outbox (2026-11-22)

### 10.1 Objetivo, documentação consultada e escopo

Este adendo registra a inspeção somente leitura do histórico de migrations e do catálogo PostgreSQL/Supabase, com a finalidade de preservar configurações já existentes e impedir a recriação de objetos, migrations, testes ou mecanismos já implementados.

Antes da inspeção foram consultados este registro SIGS, a ADR-001 (notificações orientadas a eventos para as outboxes) e os registros técnicos disponíveis no repositório. A ADR-001 determina que a outbox persistida continue sendo a fonte durável, que o polling permaneça como fallback e que notificações não substituam os mecanismos de claim/finalização existentes.

Escopo executado: leitura do histórico de migrations, definições de funções, colunas, constraints, índices, triggers, políticas RLS e privilégios das quatro tabelas Outbox. Nenhuma migration foi aplicada; nenhum DDL/DML, teste destrutivo, sincronização operacional, alteração de credencial ou escrita em integração externa foi executado.

### 10.2 Inventário confirmado no projeto Supabase

A consulta ao histórico do projeto retornou **32 migrations registradas**. O catálogo confirmou a existência das quatro filas:

1. `patrimonios_sheets_outbox`;
2. `patrimonio_fotos_sheets_outbox`;
3. `patrimonio_fotos_drive_outbox`;
4. `patrimonio_fotos_local_outbox`.

Também foram encontrados objetos já implementados que devem ser reutilizados e não recriados por suposição:

- Triggers de enfileiramento automático de patrimônio e fotos (`trg_gti_*`).
- Funções de claim/finalização/falha do Drive: `claim_patrimonio_fotos_drive_outbox`, `finalize_patrimonio_fotos_drive_outbox` e `fail_patrimonio_fotos_drive_outbox`.
- Funções de claim/conclusão/falha da fila local: `claim_patrimonio_fotos_local_outbox`, `complete_patrimonio_fotos_local_outbox` e `fail_patrimonio_fotos_local_outbox`.
- Funções de reconciliação de patrimônio e fotos Sheets.
- Índices, chaves primárias/estrangeiras, constraints de status e contadores de tentativas.

A fila local de fotos já possui `worker_id`, `lease_token`, `lease_expires_at`, `processando_em`, `tentativas` e `proxima_tentativa_em`. Esse desenho é uma referência existente, não uma autorização para copiar a implementação sem revisar suas condições de expiração, tentativas e finalização.

### 10.3 Correspondência entre histórico Supabase e repositório

A inspeção identificou as seguintes situações:

| Migration/objeto | Evidência no Supabase | Situação no Git consultado |
|---|---|---|
| `20261012213050_gti_auto_enqueue_outboxes` | Registrada no histórico; funções e triggers correspondentes presentes | SQL recuperado na branch histórica `chore/gti-outbox-triggers-prod-migration-20261012`; não localizado em `main` |
| `20261012213108_fix_gti_photo_outbox_trigger_routing` | Registrada no histórico; roteamento atual de fotos presente | SQL recuperado na mesma branch histórica; não localizado em `main` |
| `20261003230654_add_safe_drive_outbox_claim` | Migration registrada; função de claim Drive presente | Arquivo não localizado em `main` |
| `20261003235815_harden_drive_outbox_finalize_idempotent` | Migration registrada; função de finalização Drive presente | Arquivo não localizado em `main` |
| `20261003235928_harden_drive_outbox_retry_dead_letter` | Migration registrada; função de falha/retry Drive presente | Arquivo não localizado em `main` |
| `20261007213327_add_local_photo_worker_leases` | Migration registrada; funções e colunas de lease local presentes | Arquivo não localizado em `main` |

A branch histórica que contém os dois SQLs de triggers está **2 commits à frente e 6 atrás de `main`** na comparação consultada. Portanto, não se deve mesclá-la integralmente nem copiar seus commits sem revisão de dependências e diffs. Os dois arquivos SQL foram recuperados e comparados em conteúdo com o comportamento dos objetos encontrados no catálogo; a reconciliação de histórico Git ainda precisa ser feita de forma controlada.

As migrations-base `20260930170000_patrimonios_google_sheets_outbox.sql`, `20261001190000_harden_outbox_and_private_photo_storage.sql`, `20261002102325_harden_outbox_rls_deny_public_roles.sql` e `20261003190000_harden_outbox_health_view_public_grants.sql` foram localizadas em `main`. A existência desses arquivos não substitui a comparação integral entre cada definição versionada e o estado atualmente aplicado.

Foi observado também hardening de privilégios no catálogo: as funções Outbox consultadas não concedem EXECUTE a `anon` ou `authenticated`, e concedem execução a `service_role`. O arquivo/timestamp exato responsável por cada concessão ainda não foi reconciliado com segurança; não criar uma migration substituta com base apenas nesse resultado.

**Classificação:** há migrations aplicadas sem arquivo correspondente em `main`, duas delas recuperadas em uma branch histórica, e outras quatro identificadas pelo histórico/catálogo que ainda exigem recuperação do SQL original e comparação. Não é evidência de que as migrations não tenham sido aplicadas; é uma divergência de rastreabilidade/versionamento.

### 10.4 Achados de segurança e lease no catálogo

- As tabelas Sheets consultadas não concedem privilégios de tabela a `anon` ou `authenticated`.
- `patrimonio_fotos_drive_outbox` e `patrimonio_fotos_local_outbox` apresentam privilégios de tabela para essas roles. RLS está habilitado; a tabela Drive possui política restritiva de negação para roles públicas, enquanto a tabela local não apresentou política própria na consulta. A ausência de política, com RLS habilitado, resulta em negação por padrão; ainda assim, os privilégios concedidos são mais amplos que o necessário e devem ser revisados em gate próprio, sem alteração automática.
- As funções de claim/finalização/falha examinadas estão restritas a `service_role` no privilégio EXECUTE.
- O claim da fila local utiliza `FOR UPDATE SKIP LOCKED` e token de lease. Não foi localizada função de heartbeat/renovação no catálogo consultado.
- As funções locais de conclusão/falha validam o token, mas a inspeção não confirmou validação explícita de que `lease_expires_at` ainda esteja no futuro.
- As rotinas Drive ainda usam identificação por evento/ID, sem token de fencing; a recuperação de leases expirados e o orçamento de tentativas precisam ser avaliados em conjunto com os workers e migrations originais.

Esses achados não autorizam mudanças em RLS, grants, funções ou schema. Qualquer correção exige proposta isolada, testes e autorização específica do proprietário.

### 10.5 Preservação de testes e configurações existentes

Não foram repetidos testes já executados pelas PRs #90–#96 nem workflows operacionais. A inspeção do banco foi composta por consultas de catálogo/SELECT. O resultado de CI das PRs continua vinculado aos respectivos commits e não foi reinterpretado como teste de integração em produção.

Não reconstruir os SQLs ausentes manualmente enquanto o original puder ser recuperado de branches, commits, PRs ou histórico. Não aplicar `db push`, `migration up`, `apply_migration`, nem atualizar a tabela de histórico de migrations durante esta reconciliação.

### 10.6 Gates seguintes

1. Continuar a busca pelos quatro SQLs aplicados que não foram encontrados em `main` nem nas branches candidatas já verificadas; não declarar a busca exaustiva até examinar as demais referências acessíveis. Preservar conteúdos originais e metadados. Os dois SQLs de triggers já foram recuperados na branch histórica.
2. Recuperar e identificar o SQL/timestamp de hardening de privilégios, sem presumir nome ou versão.
3. Comparar cada SQL original com `pg_get_functiondef`, colunas, constraints, índices, triggers, RLS e grants do catálogo; registrar diferenças explícitas.
4. Construir uma matriz final de migrations aplicadas, arquivos em `main`, arquivos em branches históricas e divergências de conteúdo.
5. Somente após a matriz e revisão do proprietário, propor eventual reconciliação documental/versionada. Não executar migrations nem modificar schema como parte desses gates.
6. Em gate separado, desenhar a evolução dos leases aproveitando as funções e colunas já existentes, sem criar uma segunda implementação de claim/heartbeat.

**Limites confirmados neste adendo:** nenhuma migration, alteração de schema, escrita em Supabase/PostgreSQL, execução de testes destrutivos, sincronização Sheets/Drive, alteração de secrets, merge ou deploy foi realizada. Este registro é documental e não declara a integração operacional validada.


### 10.7 Complemento de recuperação — timestamps reais e SQLs não localizados (2026-11-22)

Nova consulta ao histórico oficial do Supabase confirmou 32 versões e corrigiu três divergências de timestamp observadas no registro anterior:

| Versão aplicada no Supabase | Arquivo encontrado em `main` | Situação |
|---|---|---|
| `20260930171805_patrimonios_google_sheets_outbox` | `20260930170000_patrimonios_google_sheets_outbox.sql` | Mesmo nome funcional, timestamp diferente; equivalência integral ainda não demonstrada |
| `20261001183052_harden_outbox_and_private_photo_storage` | `20261001190000_harden_outbox_and_private_photo_storage.sql` | Mesmo nome funcional, timestamp diferente; equivalência integral ainda não demonstrada |
| `20261001184053_harden_trigger_function_execute_privileges` | Não localizado em `main` nem nas branches candidatas consultadas | SQL original ainda não recuperado |
| `20261002102325_harden_outbox_rls_deny_public_roles` | Mesmo timestamp e nome em `main` | Correspondência nominal; comparar integralmente com o catálogo antes de concluir equivalência |
| `20261003175946_harden_outbox_health_view_public_grants` | `20261003190000_harden_outbox_health_view_public_grants.sql` | Mesmo nome funcional, timestamp diferente; equivalência integral ainda não demonstrada |

Os três arquivos em `main` com timestamp diferente foram lidos. Seus conteúdos implementam, respectivamente, criação da Outbox de patrimônio e função de reconciliação; hardening RLS/grants e bucket privado; e revogação de acesso público à view de saúde. O fato de os nomes e conteúdos aparentarem corresponder ao propósito das migrations remotas não autoriza renomear, reaplicar ou atualizar a tabela de histórico. A equivalência precisa ser demonstrada por comparação do SQL e dos objetos resultantes.

Também foram consultadas as definições atuais de seis funções PostgreSQL:

- Drive: `claim_patrimonio_fotos_drive_outbox`, `finalize_patrimonio_fotos_drive_outbox` e `fail_patrimonio_fotos_drive_outbox`.
- Espelhamento local: `claim_patrimonio_fotos_local_outbox`, `complete_patrimonio_fotos_local_outbox` e `fail_patrimonio_fotos_local_outbox`.

A definição atual do claim Drive recupera eventos `processing` expirados para `pending`, sem aplicar o limite de tentativas nessa etapa; a nova reivindicação incrementa tentativas. A função de falha Drive aplica `p_max_attempts` e pode mover o evento para `dead_letter`. A finalização é idempotente para evento já `synced`, mas não utiliza token de propriedade do worker.

A fila local reivindica eventos expirados com novo `lease_token` e novo prazo, incrementando tentativas. A conclusão e a falha conferem `lease_token`, mas a definição consultada não condiciona a operação a `lease_expires_at > now()`; o claim também não aplica um teto de tentativas. Não foi encontrada função de heartbeat no catálogo consultado.

### 10.8 Resultado da busca de SQLs originais

Foram pesquisados os nomes exatos das migrations, histórico de commits e PRs, e branches relacionadas a Outbox, Drive, fotos, leases e sincronização. Foram testados caminhos de migration nas branches candidatas, incluindo branches de inventário Outbox, retry, reconciliação de fotos, lease de Drive e espelhamento local.

Resultado nesta rodada:

- Os dois SQLs de triggers continuam recuperados na branch histórica da PR #56.
- Os quatro SQLs `20261003230654_add_safe_drive_outbox_claim`, `20261003235815_harden_drive_outbox_finalize_idempotent`, `20261003235928_harden_drive_outbox_retry_dead_letter` e `20261007213327_add_local_photo_worker_leases` não foram encontrados em `main` nem nas branches candidatas verificadas nesta rodada.
- O SQL `20261001184053_harden_trigger_function_execute_privileges` também não foi encontrado nas referências examinadas.
- A busca não foi considerada exaustiva sobre todas as branches e commits do repositório. Portanto, não classificar os arquivos como perdidos ou inexistentes; continuam pendentes de recuperação em histórico Git mais amplo ou de fonte original confiável.

**Decisão de segurança:** não gerar SQL substituto a partir de `pg_get_functiondef`, não recriar migrations a partir do catálogo, não renomear arquivos com timestamps divergentes e não atualizar migration history. As definições atuais do banco são evidência do estado instalado, não substitutos byte-a-byte do SQL original.


### 10.9 Linhagem Git recuperada para migrations com timestamp divergente

A busca por commits ampliou a rastreabilidade de três migrations cujo nome funcional existe em `main`, mas cujo timestamp local diverge do histórico remoto:

- Commit `76845a306c47a9849cd26ae17215d7f5ac35989b` (`feat: criar outbox durável para sincronização de patrimônios`): o diff contém o SQL que corresponde ao conteúdo atual de `20260930170000_patrimonios_google_sheets_outbox.sql`. A versão remota registrada é `20260930171805`. O SQL versionado e a definição atual da tabela/função devem ser comparados antes de qualquer reconciliação de versão.
- Commit `22f2f7e6a6b6cb2709d15f7ebc5174085cde9763` (`security: bloquear outbox publico e tornar fotos privadas`): o diff contém o SQL que corresponde ao conteúdo atual de `20261001190000_harden_outbox_and_private_photo_storage.sql`. A versão remota registrada é `20261001183052`.
- Commit `0a95aafcfd4a544e00f83e1f5cc2798909bc3c88` (`security: version-control outbox health grant hardening`): o diff contém o SQL que corresponde ao conteúdo atual de `20261003190000_harden_outbox_health_view_public_grants.sql`. A versão remota registrada é `20261003175946`.

Para a migration RLS `20261002102325_harden_outbox_rls_deny_public_roles`, foram localizados o commit de conteúdo `ac5da606b27dcbe0165001dc1fe3bb4853dcdb8d` e o commit de versionamento `688e28c96e8d6e82038be1370924b01ebf66ac98`; também foi encontrado o commit `400b13fd85f97821259fb3089f9a573f1ca9e4e8`, que removeu a versão anterior do arquivo durante o alinhamento de versão.

Essas evidências recuperam a linhagem do SQL versionado, mas **não provam, isoladamente, que o conteúdo byte a byte aplicado no Supabase seja idêntico**. O histórico remoto conserva versão/nome, não o corpo SQL original. A classificação correta para as três primeiras é: conteúdo de origem versionado localizado, timestamp divergente, equivalência com a aplicação remota pendente de prova. Não renomear arquivos nem editar o histórico para forçar correspondência.

Os quatro SQLs Drive/local e o SQL de privilégios de execução permanecem sem origem SQL localizada nas referências consultadas. Os commits de implementação do worker Drive (`d5782dac5fabc36cf40926d2d7d452a43de0300b`, `808817f66908a1b85249bf3925055795c9982e5f` e `9fcefe5a94e99b3329907e00b67f26d2847b7312`) contêm alterações Python e não substituem os SQLs de migration.


### 10.10 Busca adicional em branches e commits de workers (2026-11-22)

A busca foi ampliada para branches relacionadas a Outbox, Drive, fotos, espelhamento local, leases, reconciliação e arquitetura GTI, além de commits indexados por `outbox`, `Drive outbox`, `local drive mirror worker` e termos de lease. Os caminhos exatos dos cinco SQLs pendentes foram consultados em branches adicionais de implementação e documentação; nenhum dos cinco arquivos foi recuperado nessas referências adicionais.

Foi localizado o commit `78ef0a30c0959a573d87c40c72c912060f6b13f9` (`Feat: add safe local Drive mirror worker`, 2026-10-07), que adiciona `workers/local_drive_mirror_worker.py` e testes, mas não contém a migration `20261007213327_add_local_photo_worker_leases.sql`. O worker recuperado usa chamadas REST ao Supabase, reivindica registros com PATCH condicionado a `status=pending`, incrementa `tentativas` e usa `MAX_ATTEMPTS` ao registrar falhas. O código desse commit não contém uso de `lease_token` nem `lease_expires_at`. Isso não prova que o worker seja a única implementação operacional da fila local; evidencia apenas que esse commit não é a origem do SQL de lease.

Também foi reexaminado o commit `d5782dac5fabc36cf40926d2d7d452a43de0300b`, que adiciona o worker incremental de fotos Drive. Seu SQL de claim recupera eventos `processing` expirados sem limitar tentativas nessa condição; o limite `MAX_TENTATIVAS` é aplicado ao ramo `pending` (e o commit posterior `9fcefe5a94e99b3329907e00b67f26d2847b7312` adiciona `failed` a esse ramo). O claim não incrementa tentativas quando recupera um item `processing` expirado. Esse comportamento é coerente com o risco já observado na função Drive atual e reforça a necessidade de gate próprio para lease/fencing e teto de tentativas.

**Resultado do Gate 7 nesta rodada:** nenhum dos cinco SQLs pendentes foi recuperado. Foram recuperadas evidências de implementação Python e de comportamento dos workers, que não substituem os arquivos originais. A busca continua limitada às branches e commits acessíveis e indexados pelas consultas realizadas; não declarar inexistência definitiva dos arquivos. Nenhuma migration, SQL de escrita, atualização de schema, alteração de dados ou sincronização operacional foi executada.


### 10.11 Gate 8 — reconciliação estrutural das quatro Outboxes (2026-11-22)

Auditoria executada por consultas exclusivamente `SELECT` ao catálogo PostgreSQL e ao histórico de migrations. Nenhum dado operacional de patrimônio/foto foi consultado; não houve DDL/DML, alteração de privilégios, migration, sincronização ou execução de worker.

**Contagem e objetos confirmados**
- Histórico `supabase_migrations.schema_migrations`: **34 versões**, não 32. A contagem anterior registrada na seção 10 estava incompleta e deve ser considerada corrigida por este resultado.
- Quatro tabelas Outbox presentes: `patrimonios_sheets_outbox`, `patrimonio_fotos_sheets_outbox`, `patrimonio_fotos_drive_outbox` e `patrimonio_fotos_local_outbox`.
- As quatro tabelas estão com RLS habilitado; nenhuma está com `FORCE ROW LEVEL SECURITY`.
- Quatro triggers GTI ativos foram encontrados: três em `patrimonio_fotos` (INSERT, UPDATE de metadados Drive e UPDATE de metadados Storage) e um em `patrimonios` (INSERT e UPDATE de campos patrimoniais). Todos apontam para `gti_enqueue_foto_outboxes()` ou `gti_enqueue_patrimonio_sheets_outbox()`.
- Ambas as funções de trigger são `SECURITY DEFINER`, com `search_path=pg_catalog, public`. A definição de fotos roteia para Sheets quando há identificadores/URL Drive preenchidos; caso contrário, cria evento na fila Drive. Alterações de metadados Storage voltam a enfileirar Drive; mudanças em campos Drive roteiam para Sheets quando há dados suficientes.

**Estrutura e integridade**
- As quatro tabelas possuem PK, CHECK de status e CHECK `tentativas >= 0`.
- Patrimônio Sheets mantém UNIQUE `(patrimonio_id, evento)`, FK para `patrimonios` com `ON DELETE CASCADE), índice de claim e índice por patrimônio.
- Fotos Sheets tem FK para patrimônio/foto com `ON DELETE CASCADE`, índice parcial de eventos pendentes/failed e UNIQUE parcial `(foto_id, evento)` quando `foto_id IS NOT NULL`.
- Fotos Drive tem UNIQUE `(foto_id, evento)`, FKs para foto e patrimônio sem ação explícita de cascade, e índice de claim por `(status, proxima_tentativa_em, id)`.
- Fotos local tem UNIQUE `(foto_id)`, FKs sem cascade explícito, índices de claim/FIFO/Drive/patrimônio e estados adicionais `verified`, `drive_delete_pending` e `completed`.
- A tabela local contém `worker_id`, `lease_token` UUID e `lease_expires_at`, além de campos de fila e verificação local.

**RLS e privilégios efetivos — achado prioritário**
- As quatro tabelas têm RLS habilitado.
- Políticas restritivas `deny_anon_authenticated_unless_backend` com `USING false` e `WITH CHECK false` existem em patrimônio Sheets, fotos Sheets e fotos Drive.
- **Fotos local não possui política própria registrada em `pg_policies`.** Com RLS habilitado e sem política permissiva, o acesso por linha fica negado por padrão. Não é evidência de exposição atual; é uma diferença de configuração que deve ser reconciliada com o desenho de segurança esperado.
- Apesar disso, `has_table_privilege` confirma privilégios efetivos de tabela SELECT/INSERT para `anon` e `authenticated` em fotos Drive e fotos local. Em Drive, a política restritiva bloqueia as operações por linha; em local, a ausência de política permissiva produz deny-by-default. Os privilégios amplos continuam sendo concessões desnecessárias e ampliam o risco de uma futura política permissiva ser adicionada sem perceber os grants preexistentes.
- Para patrimônio Sheets e fotos Sheets, `anon` e `authenticated` não têm SELECT/INSERT; `service_role` tem os privilégios operacionais nas quatro tabelas.
- As oito funções consultadas (seis funções worker Drive/local e duas funções de trigger) são `SECURITY DEFINER`. EXECUTE está negado para `anon` e `authenticated` e permitido para `service_role`. As funções Drive usam `search_path=pg_catalog, public`; funções locais usam `search_path=public`. Não foi realizada alteração de grants ou search_path.

**Conclusões e limites**
1. A presença das quatro tabelas, quatro triggers, constraints, índices, policies e funções confirma o estado estrutural consultado, mas não prova que cada arquivo SQL local corresponda byte a byte ao SQL aplicado.
2. O conjunto de políticas RLS é assimétrico: a tabela local depende de deny-by-default, enquanto as outras três possuem política restritiva explícita. Os grants de tabela anon/authenticated em Drive/local merecem correção planejada e revisão do proprietário; nenhuma revogação foi executada.
3. As funções privilegiadas estão protegidas contra EXECUTE direto por anon/authenticated conforme `has_function_privilege`; isso não substitui revisão de seus corpos e do modelo de autorização.
4. A comparação estrutural dos objetos foi feita; a comparação integral de cada função com seu SQL original permanece limitada pelos cinco arquivos ainda não recuperados.
5. Não foi feita consulta de contagem/estado de eventos operacionais, nem teste de chamada das funções, para evitar interferir no processamento real.

**Próximo gate recomendado:** Gate 9 — revisão de segurança sem escrita, com foco nos grants residuais anon/authenticated de fotos Drive/local, ausência de policy explícita na fila local, SECURITY DEFINER/search_path e fencing/expiração/limite de tentativas. O Gate 9 deve produzir proposta de correção e testes em branch isolada; não executar REVOKE, CREATE POLICY, ALTER FUNCTION ou qualquer DDL no projeto remoto sem autorização específica.


### 10.12 Gate 9 — revisão de segurança de funções e workers (2026-11-22)

Revisão estática de definições SQL obtidas por `pg_get_functiondef` e leitura de arquivos versionados no GitHub. Não houve invocação de funções worker, chamadas REST, processamento de filas, alteração no banco, teste de integração com serviços externos ou escrita em Sheets/Drive.

**Achados confirmados nas funções SQL instaladas**
1. `claim_patrimonio_fotos_drive_outbox` recupera todos os registros `processing` antigos diretamente para `pending`, sem verificar `tentativas` contra teto. Depois reivindica pending e incrementa tentativas. Assim, a recuperação de lease expirado pode continuar indefinidamente.
2. A reivindicação Drive usa `FOR UPDATE SKIP LOCKED`, mas não emite `lease_token` nem identifica um proprietário do claim. `finalize_patrimonio_fotos_drive_outbox` e `fail_patrimonio_fotos_drive_outbox` recebem apenas o ID; não verificam token de posse nem validade de lease. Um worker atrasado pode finalizar ou reclassificar um evento que já foi retomado por outro worker.
3. `claim_patrimonio_fotos_local_outbox` gera UUID por claim e recupera leases expirados, mas não limita `tentativas` no ramo de recuperação. Portanto, também permite reclaims sem teto.
4. `complete_patrimonio_fotos_local_outbox` e `fail_patrimonio_fotos_local_outbox` conferem `status='processing'` e `lease_token`; isso fornece fencing contra um token substituído. Contudo, não verificam `lease_expires_at > now()`. Um worker cujo lease expirou, mas ainda não foi substituído, ainda pode completar/falhar o evento.
5. `fail_patrimonio_fotos_local_outbox` não valida explicitamente limites de `p_max_attempts` ou sinal de `p_retry_after`; a lógica depende dos parâmetros recebidos pelo chamador.
6. As funções Drive e local são `SECURITY DEFINER`; grants EXECUTE para anon/authenticated seguem negados conforme Gate 8. Funções Drive qualificam objetos como `public.*` e usam `search_path=pg_catalog, public`; funções locais usam `search_path=public`. A revisão não identificou referência não qualificada a objetos de aplicação nos corpos lidos, mas recomenda-se padronizar `pg_catalog, public` e qualificar objetos em uma alteração futura testada.

**Achados nos workers Sheets versionados no branch padrão**
- `inventario_sheets_outbox_worker.py`: `claim_batch` reivindica pending/failed sem filtrar `tentativas < max_attempts`; `reset_stale` transforma processing expirado em failed sem aplicar teto. A função `mark` só envia a dead-letter após falha subsequente. Isso permite tentativas excedentes em registros failed e recuperação sem limite estrito.
- `sheets_outbox_worker.py`: o claim de fotos seleciona pending/failed sem filtro de tentativas; `reset_stale` move processing expirado para failed sem aplicar o limite. `mark` aplica dead-letter após falha, mas não impede novo claim de um item já acima do teto.
- `sincronizador_google_sheets.py`: o claim permite recuperar processing expirado sem verificar teto e mantém o contador de tentativas inalterado no ramo expirado. A finalização por ID não inclui token/fencing. A rotina de sincronização também executa preflight estrutural com aplicação de alterações no Sheets; portanto, não deve ser tratada como operação read-only.
- `workers/local_drive_mirror_worker.py`: o worker REST reivindica apenas status pending por PATCH condicional, sem token/lease; o caminho observado não recupera registros processing expirados. Há risco de eventos ficarem presos em processing após interrupção. A rotina live também pode remover arquivos Drive, condicionada a flags de execução, e não foi invocada nesta auditoria.

**Relação com correções em branches/PRs já existentes**
- PR #91 corrige seleção de failed no consumidor Sheets.
- PR #93 corrige o limite de tentativas para leases expirados no consumidor principal e worker patrimonial Sheets.
- PR #95 adiciona guarda para o PostgreSQL descartável usado nos testes concorrentes.
- Esses ajustes não demonstram cobertura do worker dedicado de fotos `sheets_outbox_worker.py`, do worker Drive, nem do worker local/rotina REST. A revisão do código no branch padrão não substitui uma inspeção final dos heads empilhados das PRs antes de eventual integração.

**Classificação e plano de correção proposto (não aplicado)**
- **P0 — fencing Drive:** introduzir lease token por claim e exigir token vigente nas operações finalize/fail; limitar tentativas também ao recuperar processing expirado.
- **P0 — limite local:** aplicar teto de tentativas na seleção/reclaim de leases expirados e enviar esgotados diretamente a dead_letter.
- **P1 — validade local:** exigir `lease_expires_at > now()` em complete/fail; validar parâmetros de retry e teto.
- **P1 — Sheets:** unificar claim/reset/mark com máximo de tentativas em todos os ramos e fencing por lease token; cobrir os dois workers e o sincronizador alternativo.
- **P1 — worker REST local:** migrar para função de claim/complete/fail com lease token ou implementar protocolo equivalente atômico; definir recuperação de processing e fencing. Não manter PATCH por status como único mecanismo de posse.
- **P2 — hardening SQL:** padronizar `search_path=pg_catalog, public`, manter referências qualificadas e validar grants/policies após desenho de autorização explícito.

**Critérios mínimos de testes antes de qualquer proposta de integração**
- Dois workers concorrentes: somente um obtém cada lease.
- Worker A expira; worker B obtém novo token; finalize/fail de A é rejeitado.
- Token válido com lease expirado é rejeitado.
- Última tentativa falha e lease expira: dead_letter, sem nova reivindicação.
- Failed já acima do teto não é reivindicado.
- Interrupção de worker REST permite recuperação sem permitir finalização por proprietário antigo.
- Testes PostgreSQL em instância descartável com guarda de segurança; testes Sheets/Drive com mocks, sem credenciais reais.

**Limitações**
- Leitura de código foi feita no branch padrão e em referências de PRs conhecidas; não foi uma comparação integral de todos os heads/branches.
- Nenhuma função foi chamada e nenhum registro operacional foi lido ou alterado.
- Nenhuma correção de código ou SQL foi implementada neste gate.
- As conclusões sobre funções instaladas derivam dos corpos efetivamente consultados; as conclusões sobre workers aplicam-se aos arquivos/versões examinados, não necessariamente a todo artefato de execução atualmente implantado.

**Próximo gate recomendado:** Gate 10 — desenho técnico e implementação isolada do protocolo uniforme de leases/fencing e limites de tentativas, começando por testes unitários e PostgreSQL descartável. Não aplicar migrations, REVOKE, CREATE POLICY, ALTER FUNCTION ou qualquer alteração de produção sem autorização específica.


## 11. Gate 10A — especificação uniforme de leases e fencing (2026-11-22)

### 11.1 Autorização e limites

O proprietário autorizou o Gate 10 em branch isolada, com PR draft, testes descartáveis e produção/banco remoto intocados. Esta entrega limita-se à especificação técnica e ao registro de governança. Não houve alteração em worker/runtime, migration, schema, função SQL instalada, workflow operacional ou credencial.

### 11.2 Artefato técnico

Foi criado o documento `docs/architecture/OUTBOX_LEASE_FENCING_PROTOCOL.md`, que especifica:
- token de fencing novo por geração de claim, worker_id observável e lease_expires_at;
- claim atômico com FOR UPDATE SKIP LOCKED, incremento de tentativas em toda reivindicação e dead_letter direto para leases expirados esgotados;
- heartbeat, complete e fail condicionados a token exato e lease ainda vigente;
- uso de clock_timestamp() para validade temporal;
- idempotência dos efeitos externos e limitação da garantia: fencing no banco não impede sozinho um efeito externo já iniciado por worker obsoleto;
- dependências separadas para Drive, fotos local, Sheets patrimônio, Sheets fotos e sincronizador alternativo;
- sequência de migração/cutover, testes concorrentes, rollback e critérios de aceite.

### 11.3 Decisões de segurança

1. Não criar migration ou DDL com base apenas no catálogo ou em pg_get_functiondef.
2. Não presumir que o schema das quatro filas seja homogêneo; a fila local já possui campos de lease, enquanto as demais precisam de reconciliação individual.
3. Não considerar heartbeat como mecanismo para ressuscitar lease expirado.
4. Não usar finalização por ID como fallback quando token/lease não corresponderem.
5. Não declarar exactly-once entre PostgreSQL e Sheets/Drive/filesystem; a solução requer efeitos idempotentes e reconciliação.
6. Não habilitar worker novo enquanto consumidores antigos ainda puderem finalizar por ID sem fencing.

### 11.4 Bloqueios para implementação de runtime

A implementação de runtime permanece bloqueada até:
- recuperação e reconciliação dos SQLs originais das funções/migrations Drive e local;
- mapeamento da máquina de estados local, inclusive drive_delete_pending;
- definição de contrato compatível para os dois workers Sheets e sincronizador alternativo;
- desenho de migration aditiva e funções versionadas, com revisão de SECURITY DEFINER, grants, RLS e search_path;
- testes concorrentes em PostgreSQL efêmero protegido por guarda;
- aprovação específica do proprietário para artefatos de schema.

A busca anterior não localizou cinco SQLs originais relacionados a Drive/local/privilégios nas referências examinadas. A busca não é prova de inexistência definitiva; não serão recriados a partir de funções instaladas.

### 11.5 Estado e próximo gate

- Branch isolada: `feat/outbox-lease-protocol-gate10-20261122`, baseada no head da PR #97.
- PR será aberta em draft, empilhada sobre a branch documental da PR #97.
- Escopo desta entrega: novo documento de arquitetura e este adendo append-only.
- Nenhum arquivo anterior foi removido; nenhum worker, teste de runtime, migration ou schema foi alterado.
- Próximo gate: recuperar SQLs originais e elaborar proposta de migration aditiva com testes locais descartáveis; antes de aplicar qualquer schema no projeto remoto, solicitar autorização específica e separada.

**Limites confirmados:** nenhuma consulta/escrita no Supabase remoto durante esta entrega; nenhuma função foi invocada; nenhum worker ou integração externa foi executado; nenhuma alteração em main, merge, deploy ou sincronização operacional ocorreu.


## 12. Gate 10B — reconciliação da origem Git dos SQLs de Outbox (2026-11-22)

### 12.1 Escopo

Busca read-only ampliada a branches, árvores Git, arquivos e commits do repositório. Nenhuma conexão/consulta Supabase foi realizada nesta rodada; nenhum worker, integração ou workflow operacional foi executado.

### 12.2 Artefatos próximos descartados como equivalentes

- Encontrado `supabase/migrations/20261013130000_gti_drive_folder_lease.sql` na branch `fix/gti-drive-folder-lease-gate-20261013`. O SQL cria lease para serializar criação/verificação de pastas Drive por patrimônio, com tabela `gti_drive_folder_leases` e funções acquire/release. **Não** reivindica eventos da tabela `patrimonio_fotos_drive_outbox`, não altera estado de eventos e não substitui claim/finalize/fail da Outbox.
- Encontrado `supabase/migrations/20261001154000_harden_trigger_function_execute_privileges.sql`, que protege somente `validar_movimentacao_patrimonio()`. O histórico remoto registra `20261001184053_harden_trigger_function_execute_privileges` no contexto de hardening das funções Outbox. Timestamp e objeto diferem; não há prova de equivalência. Não classificar o arquivo encontrado como origem da migration remota.

### 12.3 Evidências de workers

- O commit `d5782dac5fabc36cf40926d2d7d452a43de0300b` adiciona worker Drive legado: claim SQL direto com SKIP LOCKED; ramo pending com teto; ramo processing expirado sem teto e sem incremento de tentativas; finalização por ID sem token. O commit `9fcefe5a94e99b3329907e00b67f26d2847b7312` adiciona failed ao ramo elegível, mas não resolve as demais lacunas observadas.
- O commit `78ef0a30c0959a573d87c40c72c912060f6b13f9` adiciona worker REST local: claim por PATCH condicionado a status=pending, sem token/expiry; caminho examinado não recupera processing expirado; há estados intermediários `drive_delete_pending` e `completed`.
- Essas evidências se aplicam aos commits examinados e não provam exclusividade nem estado de todos os artefatos implantados.

### 12.4 Resultado da busca dos SQLs

Após a busca ampliada por branches/árvores e por mensagens de commits, os cinco arquivos exatos permanecem não recuperados nas referências examinadas:
- `20261003230654_add_safe_drive_outbox_claim.sql`;
- `20261003235815_harden_drive_outbox_finalize_idempotent.sql`;
- `20261003235928_harden_drive_outbox_retry_dead_letter.sql`;
- `20261007213327_add_local_photo_worker_leases.sql`;
- `20261001184053_harden_trigger_function_execute_privileges.sql`.

Busca de commits por nome exato sem resultados não prova inexistência em refs apagadas, forks, backups ou objetos locais. O relatório `docs/architecture/GATE10B_OUTBOX_SQL_ORIGIN_RECONCILIATION.md` registra branches, blobs, classificação dos artefatos, limites e fontes adicionais de recuperação.

### 12.5 Decisão e bloqueios

1. Não reconstruir migrations a partir de `pg_get_functiondef`.
2. Não renomear ou copiar arquivos com timestamp/objeto diferentes para satisfazer o histórico remoto.
3. Não alterar `schema_migrations`, schema, funções instaladas, grants ou policies.
4. Próxima fonte prioritária: checkout local do proprietário, objetos Git, refs, reflogs, bundles e backups; busca somente leitura.
5. Se os originais não forem recuperados, desenhar migration nova, aditiva e versionada, baseada em especificação aprovada e estado de catálogo novamente confirmado; apresentar compatibilidade/cutover/rollback antes de qualquer aplicação.

**Limites confirmados:** somente leitura GitHub; nenhum acesso ao Supabase, nenhum SQL, nenhuma execução de função, worker ou integração externa; nenhuma alteração em main, merge ou deploy.


## 13. Gate 10C — estado operacional remoto e correções isoladas (2026-11-22)

### 13.1 Escopo e segurança

Foi realizada leitura direta do projeto Supabase conectado e revisão do código/PRs no GitHub. Consultas foram somente leitura. Foram criadas/atualizadas branches e PRs de código em modo draft para correção e validação automatizada. Nenhuma migration foi aplicada ao Supabase remoto; nenhum worker operacional foi invocado; nenhuma fila foi processada; nenhuma escrita foi feita no Google Sheets ou Drive; nenhum segredo foi alterado; nenhuma PR foi mesclada e nenhum deploy foi executado.

### 13.2 Estado observado no Supabase

- Projeto `gti-inventario`: ativo/saudável; Edge Function `outbox-drive-worker` ativa na versão 22.
- Bucket `patrimonio-fotos`: privado; limite configurado de 1 MiB; os 56 objetos observados correspondem aos 56 registros de fotos; maior objeto observado: 305.625 bytes.
- Outbox Drive de fotos: 56 eventos sincronizados; view de reconciliação registrou 56 em estado `ok`.
- Outbox Sheets de patrimônio: 91 eventos sincronizados.
- Outbox Sheets de fotos: 54 sincronizados e 2 em `dead_letter`. Os dois eventos estão associados ao patrimônio `98654345` e falharam após 12 tentativas porque a linha não foi localizada na aba `Almoxarifado GTI-SESA-SEDE`.
- Outbox de espelhamento local: 8 eventos `pending` desde 2026-10-07, sem `caminho_local`, `sha256_local` ou tentativas registradas.
- A view `patrimonio_fotos_sheets_reconciliation` conta `pending/processing/failed`, mas exclui `dead_letter` de `eventos_pendentes` e `eventos_falhos`. A view usa `security_invoker=true`; leitura é concedida a `service_role`, não a `anon/authenticated`.
- As funções privilegiadas de Outbox consultadas não concedem execução a `anon` ou `authenticated`.

Os estados acima são um snapshot de leitura; não representam uma reconciliação visual independente do Google Sheets nem confirmação de cada arquivo no Drive.

### 13.3 Correções isoladas em andamento

- **PR #66 — Drive folder routing/lease:** a branch adiciona lease por patrimônio, renovação/token guard, revalidação de pasta e testes. Foi incluída validação da migration em PostgreSQL descartável no CI. A execução isolada da migration foi concluída com sucesso no SHA `41afc7d50eff07b6222f89aed48734d103466e38`, incluindo acquire/renew, token incorreto, expiração, reacquisição, release, grants e duas sessões concorrentes. A PR permanece draft, empilhada sobre a PR #90; migration remota não aplicada.
- **PR #77 — Outbox de fotos para Sheets:** foi corrigida a comparação da leitura posterior para preservar posições reais quando há lacunas entre fotos (por exemplo, posições 1 e 3). O teste usa mocks e não chama serviços externos. Também foi portada a política de backoff com jitter e respeito a `Retry-After` da PR #90. Os workflows do novo head precisam concluir antes de qualquer aprovação. A view SQL citada em 13.2 continua pendente de correção aditiva após recuperação da linhagem de migrations.
- **PR #100 — autorização administrativa:** centraliza a decisão em `usuario_e_admin()`, usando a identidade autenticada e `email.admin_email`, em vez de depender de `usuario_papel` que o login não grava. Inclui testes para identidade normalizada, usuário comum, sessão ausente e configuração ausente. A PR está draft e empilhada sobre a PR #90.

### 13.4 Dependências e CI

A `main` foi identificada com versões vulneráveis de `oauthlib 4.0.0`, `pyasn1 0.6.4` e `tornado 6.5.9`. A PR #90 atualiza para `oauthlib 4.0.1`, `pyasn1 0.6.5` e `tornado 6.6.1`; no SHA `6100d4d9c248ea947cd729ee1aaadab64d48e680`, os workflows Python, CI, System Audit, Security e wake-up contract foram observados com sucesso. A branch da PR #90 recebeu ajuste posterior para permitir que CI/System Audit também rodem em PRs empilhadas sob branches `fix/**`; os workflows desse novo head estavam em execução no momento do registro.

As falhas de `pip-audit` observadas nos primeiros ciclos das PRs #66, #77 e #100 correspondem às dependências ainda presentes na `main`, não aos testes funcionais das correções. Os PRs dependentes permanecem bloqueados até que a PR #90 seja integrada e os checks sejam repetidos sobre a base final.

### 13.5 Bloqueios que permanecem

1. Recuperar os cinco SQLs originais listados no Gate 10B; não reconstruí-los a partir do catálogo remoto.
2. Resolver os dois eventos `dead_letter` de fotos do patrimônio `98654345` com reconciliação controlada da linha/ID no Sheets; não criar linha automaticamente.
3. Projetar migration aditiva para que a view de reconciliação inclua `dead_letter`, após confirmar a cadeia de migrations e compatibilidade dos consumidores.
4. Diagnosticar e recuperar os oito eventos pendentes do espelhamento local; não processar antes de identificar o worker, raiz local e contrato de lease.
5. Validar a execução agendada dos workers e a leitura real da planilha/Drive com conectores autorizados, sem expor credenciais.
6. Completar CI, System Audit e revisão independente nas PRs empilhadas.

### 13.6 Próxima sequência segura

1. Aguardar e verificar os workflows atualizados da PR #90.
2. Confirmar os testes Python, CI, System Audit e Security nas PRs #66, #77 e #100 sobre a base corrigida.
3. Reconciliar conflitos/commits divergentes antes de qualquer merge; manter PRs em draft enquanto houver checks pendentes.
4. Recuperar a linhagem SQL original no checkout local/backups e atualizar este registro de forma append-only.
5. Somente depois de todos os gates, preparar plano de homologação controlada e solicitar autorização separada para qualquer alteração remota.

**Decisão:** o sistema ainda não está liberado para produção. Os fluxos de Drive/Sheets têm componentes ativos e dados sincronizados, mas há eventos em quarentena, fila local parada, lacuna de reconciliação SQL e gates de CI/revisão ainda pendentes. Nenhuma liberação deve ser declarada com base apenas neste snapshot.


### 13.7 Revisão adicional de recuperação e classificação do espelho local (2026-11-22)

**Outbox Sheets — limite de tentativas:** a revisão posterior da PR #77 encontrou que `claim_batch` não filtrava `tentativas < max_attempts`, e `reset_stale` convertia todo `processing` expirado em `failed`, inclusive quando o teto já havia sido atingido. Isso permitia uma reivindicação extra e podia deixar eventos exauridos fora de `dead_letter`. A PR #77 foi atualizada para mover eventos exauridos de `pending/failed` diretamente a `dead_letter`, filtrar o teto no claim e classificar `processing` expirado conforme as tentativas. Foram adicionados testes para ambos os caminhos; CI ainda precisa concluir.

**Espelho local — reclassificação:** a leitura adicional confirmou 8 eventos `pending`, total de 479.689 bytes (0,457 MiB), todos sem caminho/hash local e sem tentativas. O worker `workers/local_drive_mirror_worker.py` tem gate explícito de 1 GiB de pendências antes de iniciar processamento; portanto, o volume atual está muito abaixo do limiar e a ausência de `caminho_local/sha256_local` é compatível com o comportamento intencional de espera. O script também opera em dry-run por padrão e exige `--live` mais `LOCAL_MIRROR_ALLOW_DELETE=true` para remover o arquivo original do Drive após validação local.

**Decisão revisada:** os 8 eventos locais não são classificados como bloqueio da funcionalidade principal de inventário/Drive/Sheets neste snapshot. São uma fila derivada e condicionada ao limiar de 1 GiB; permanecem pendentes até que o requisito de espelhamento local seja explicitamente ativado. Não executar `--live`, não habilitar exclusão do Drive e não alterar o limiar sem autorização operacional específica. A existência de agendamento automático não foi comprovada nesta rodada.


### 13.8 Resultado dos workflows após correções (2026-11-22)

Foram consultados os resultados dos workflows dos heads abaixo; todos os jobs listados terminaram com conclusão `success`:

| PR | Head validado | Checks concluídos |
|---|---|---|
| #90 | `0842177e4b62357eacf6555bc20310da0f50982b` | Testes Python, CI, Security, System Audit e Event wake-up contract |
| #66 | `cd57ebf2070300c613e4eb8ba3db37334c6d2aba` | Testes Python, CI, Security, System Audit e migration Drive lease em PostgreSQL descartável |
| #77 | `a43261a1f50f1640ace16361f99406f01aec6fa7` | Testes Python, CI, Security e System Audit |
| #100 | `a97bd35b5cb0e412706a8455288e8c656d802676` | Testes Python, CI, Security e System Audit |

As PRs #66, #77 e #100 permanecem em draft e empilhadas sobre a branch da PR #90. Checks verdes validam os commits examinados, não equivalem a revisão independente, merge, homologação com integrações reais ou implantação. Após a integração da PR #90, cada PR dependente deverá ser retargeted para `main`, reconciliada sua base e repetidos os workflows.

**Decisão do gate:** código e testes isolados dos três bloqueadores abordados estão aprovados pelos workflows; a liberação de produção continua bloqueada por revisão/integração, reconciliação SQL, eventos de fotos em `dead_letter`, validação externa de Sheets/Drive e gates de homologação.
