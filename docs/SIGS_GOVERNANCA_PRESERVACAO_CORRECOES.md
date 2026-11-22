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
