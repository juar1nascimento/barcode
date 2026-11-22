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

**CI:** no momento do registro, os workflows de Testes Python e Security/CodeQL estavam em execução. Não declarar aprovação até consultar a conclusão real no GitHub Actions. A PR não foi mesclada.

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
- Se encontrar regressão, apresentar evidências, impacto, diff proposto e testes necessários; aguardar autorização expressa do proprietário antes de alterar código.
- Se o estado de CI estiver em andamento ou indisponível, registrar exatamente esse estado; não inferir sucesso.
- Não registrar segredos, tokens, IDs privados de planilhas ou valores de credenciais.

### Selo nas configurações

A interface administrativa SIGS passa a exibir o indicador:

**🛡️ PRESERVAÇÃO DE CORREÇÕES — POLÍTICA ATIVA**

O selo é informativo e visível somente ao administrador autenticado. Não é um mecanismo de proteção de branch do GitHub nem substitui permissões, checks obrigatórios, revisão ou autorização humana. Não há botão para desativá-lo nesta etapa.

## 5. Rotina diária das 08:00

A automação denominada **Auditoria diária GTI SESA** está cadastrada com recorrência diária às 08:00, fuso `America/Sao_Paulo`, porém foi encontrada desabilitada/pausada em 2026-11-22. Portanto, não afirmar que está executando até ser reativada pelo proprietário.

Quando habilitada, deve:
1. Consultar PRs e workflows e diferenciar sucesso, falha, execução em andamento e ausência de dados.
2. Comparar o estado atual com os commits/PRs já registrados neste documento.
3. Acrescentar novo registro datado, sem sobrescrever os registros anteriores.
4. Preservar correções existentes e nunca fazer alteração automática no repositório.
5. Informar bloqueios, regressões e próximo gate seguro.
6. Solicitar autorização do proprietário para qualquer correção.

A configuração da automação deve permanecer pausada até autorização específica para reativação. O texto da rotina pode ser preparado sem alterar seu estado de habilitação.

## 6. Gates seguintes

- **Gate A:** concluir CI da PR #91 e revisar os logs/testes; não mesclar.
- **Gate B:** sincronizar a branch de governança com a branch local somente por fast-forward, após CI aprovado.
- **Gate C:** testar a renderização e autorização da tela de Configurações SIGS em ambiente local, sem produção.
- **Gate D:** desenhar testes de lease/heartbeat e recuperação de falhas nos dois consumidores.
- **Gate E:** definir formalmente o modelo de eventos de movimentação/baixa antes de qualquer migration.
- **Gate F:** consolidar os writers Sheets e revisar os workflows concorrentes.

## 7. Limites de execução

Nenhuma migration, escrita no Supabase/PostgreSQL, escrita no Google Sheets/Drive, sincronização operacional, deploy ou merge foi executado como parte deste registro. A integração em produção permanece bloqueada até autorização expressa do proprietário e conclusão dos gates pertinentes.
