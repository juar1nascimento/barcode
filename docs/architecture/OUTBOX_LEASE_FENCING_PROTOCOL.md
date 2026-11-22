# GTI SESA — Protocolo uniforme de leases e fencing para Outbox

- **Estado:** proposta técnica Gate 10A; não aplicada em runtime.
- **Data:** 2026-11-22.
- **Escopo:** quatro consumidores Outbox (Drive, espelhamento local, Sheets patrimônio e Sheets fotos).
- **Fonte de verdade:** PostgreSQL/Supabase; a Outbox continua durável e o polling continua como fallback.

## 1. Decisão arquitetural

Adotar um protocolo de posse temporária com fencing por token imprevisível, prazo controlado pelo relógio do banco e limite de tentativas aplicado em toda transição de claim/reclaim. O protocolo deve ser implementado por funções transacionais no PostgreSQL para as filas que usam RPC e por SQL transacional equivalente nos consumidores Python que usam conexão PostgreSQL.

Um **lease_token** identifica uma geração específica de posse, não apenas o worker. **worker_id** é metadado operacional para diagnóstico e não substitui o token. Cada nova reivindicação gera token novo, mesmo quando o mesmo processo reivindica novamente o evento.

**Importante:** fencing protege as transições no banco. Não torna atômico o efeito externo em Google Sheets, Google Drive ou filesystem. Um worker antigo pode já ter enviado uma chamada externa quando seu lease expirar. Por isso, efeitos externos precisam também ser idempotentes/condicionais e a finalização no banco deve sempre exigir o token vigente. Não prometer exactly-once entre PostgreSQL e APIs externas.

## 2. Campos canônicos propostos

Para cada fila que ainda não os possui:

| Campo | Tipo lógico | Regra |
|---|---|---|
| worker_id | text | Identificador observável do processo/instância; não é segredo |
| lease_token | uuid | Novo UUID em todo claim/reclaim |
| lease_expires_at | timestamptz | Prazo calculado pelo banco |
| processando_em | timestamptz | Momento do claim, mantido para compatibilidade/telemetria |
| tentativas | integer | Incrementa em cada nova posse |
| proxima_tentativa_em | timestamptz | Controla elegibilidade de pending/failed |

Não adicionar colunas cegamente: a fila local já possui worker/token/expiry; outras filas podem ter campos equivalentes com nomes diferentes. Primeiro reconciliar catálogo, SQL original e migration history. Não alterar nem renomear migrations históricas.

## 3. Semântica das operações

### 3.1 Claim

Parâmetros: p_worker_id, p_limit, p_lease_seconds, p_max_attempts.

Em uma única transação curta:

1. Validar worker_id não vazio, limite positivo e limitado, lease_seconds dentro de faixa operacional aprovada e max_attempts positivo.
2. Usar clock_timestamp() como referência temporal do banco.
3. Mover para dead_letter os eventos processing cujo lease expirou e cujo contador já atingiu o teto.
4. Selecionar com FOR UPDATE SKIP LOCKED os eventos elegíveis: pending ou failed com backoff vencido e tentativas abaixo do teto; ou processing com lease expirado e tentativas abaixo do teto.
5. Atualizar cada candidato para processing, incrementar tentativas exatamente uma vez, atribuir worker_id, gerar novo lease_token e definir lease_expires_at.
6. Retornar id, payload mínimo, tentativas, token e expiry.
7. Commit antes de qualquer chamada externa.

A operação deve ser atômica: nenhum consumidor pode observar um evento reivindicado sem token/expiry correspondente. O teto vale igualmente para pending, failed e reclaim de processing expirado.

### 3.2 Heartbeat

Atualização condicional por id + status='processing' + lease_token + lease_expires_at > clock_timestamp(). Somente um lease ainda vigente pode ser renovado. A nova expiry deve ser calculada pelo banco. Zero linhas atualizadas significa perda de posse; o worker deve parar de iniciar novos efeitos externos e não pode finalizar.

Heartbeat não deve ressuscitar lease expirado, mesmo que nenhum outro worker o tenha reivindicado ainda. Isso evita que um proprietário antigo recupere posse depois do prazo.

### 3.3 Complete

Atualização condicional por id, status processing, token exato e lease ainda vigente. Em sucesso: estado terminal adequado, timestamp de conclusão, limpar erro e limpar worker/token/expiry/processando_em. Se zero linhas forem afetadas, considerar lease perdido; não tentar fallback de finalização por ID.

Para filas com estados intermediários de negócio (por exemplo, espelhamento local com drive_delete_pending), definir separadamente quais transições exigem lease e quais são recuperação idempotente de saga. Não aplicar a regra genérica sem mapear a máquina de estados.

### 3.4 Fail

Atualização condicional igual a complete. Se tentativas atingiram max_attempts, estado dead_letter; caso contrário, failed com backoff limitado e jitter calculado pelo worker ou função, mas com parâmetros validados. Limpar os campos de lease. A mensagem de erro deve ser sanitizada e truncada.

### 3.5 Recover

Não manter um reset_stale genérico que transforma leases expirados em failed sem contabilização. O claim pode recuperar leases expirados diretamente, com token novo e incremento de tentativas; os esgotados devem ir para dead_letter na mesma transação. Se for necessário job de manutenção separado, ele deve aplicar exatamente o mesmo predicado de validade e teto, sem competir com claim.

## 4. Concorrência, tempo e índices

- Usar FOR UPDATE SKIP LOCKED para claim em lote; manter transação curta e não executar I/O externo dentro dela.
- Usar clock_timestamp() para validade do lease. now()/CURRENT_TIMESTAMP ficam fixos no início da transação e podem ser inadequados para validar lease em transação longa.
- Índices parciais devem refletir os predicados reais de claim e incluir ordenação determinística por id. Confirmar plano com dados de teste, sem criar índice em produção neste gate.
- Não usar advisory locks como substituto do lock de linha e do token de fencing.
- O worker deve renovar antes de consumir uma fração conservadora do prazo e tratar falha/zero-row no heartbeat como perda de posse.

## 5. Efeitos externos e idempotência

- **Sheets:** preferir localizar e atualizar por chave natural estável (ID do patrimônio/evento), evitando append sem chave/consulta de reconciliação. Token de banco não impede append duplicado já enviado por worker obsoleto.
- **Drive:** usar file_id estável e operações idempotentes; confirmar estado remoto antes de repetir exclusão/atualização.
- **Espelhamento local:** usar caminho derivado de hierarquia validada, escrita temporária + rename atômico, hash/tamanho e estado de saga; nunca apagar origem apenas por sucesso local não verificado.
- Em timeout de API externa, resultado é desconhecido: consultar estado externo e reconciliar antes de repetir ação não idempotente.
- Não prometer transação distribuída ou exactly-once. A garantia real é entrega pelo menos uma vez com efeitos idempotentes e finalização fenced.

## 6. Matriz de aplicação e dependências conhecidas

| Consumidor | Lacuna observada | Dependência antes do runtime |
|---|---|---|
| Drive Outbox | Sem token por claim; finalize/fail por ID; reclaim sem teto | Recuperar SQL original das funções/migrations ou fonte autoritativa; definir migration compatível |
| Fotos local Outbox | Token existente; reclaim sem teto; complete/fail sem validar expiry | Recuperar migration original e alinhar funções instaladas/versão local |
| Sheets patrimônio worker | Sem fencing; claim/reset com lacunas de teto no branch padrão | Conferir PRs empilhadas #91/#93/#95 e definir campos/contrato |
| Sheets fotos worker | Sem fencing; teto incompleto em claim/recovery | Definir extensão de schema e coordenar consumidor |
| Sincronizador alternativo Sheets | Finalização por ID e recuperação sem token | Consolidar ou migrar protocolo; impedir coexistência de writer antigo |

O worker REST local não reivindica leases atomicamente no código examinado; seu PATCH condicionado somente a status=pending não equivale a claim com fencing. A migração exige usar as funções RPC existentes ou substitutas versionadas, após recuperar os SQLs originais.

## 7. Sequência segura de entrega

**Fase A — concluída nesta proposta:** especificar contrato, estados, invariantes, dependências, testes e plano de cutover. Nenhum worker/runtime ou banco foi alterado.

**Fase B — bloqueada até reconciliação e aprovação:** recuperar SQL original das migrations/funções Drive e local; comparar funções instaladas e arquivos versionados; desenhar migration aditiva e funções versionadas; obter aprovação específica do proprietário para artefatos de schema. Não reconstruir migrations a partir de pg_get_functiondef.

**Fase C — implementação em branch isolada:** implementar funções e workers compatíveis em ambiente local descartável; não habilitar workflows operacionais. Fazer cutover coordenado para que nenhum worker antigo finalize por ID. Manter rollback documentado e não remover campos antigos antes de confirmar ausência de consumidores antigos.

**Fase D — testes e revisão:** concorrência PostgreSQL real descartável, testes de fencing/expiry/dead-letter, mocks de Sheets/Drive/filesystem e revisão de segurança das funções SECURITY DEFINER, grants e search_path.

**Fase E — decisão de produção:** apresentar diff, migration, plano de deploy/rollback, resultados e riscos ao proprietário. Produção exige autorização separada; esta PR não a concede.

## 8. Testes obrigatórios

1. Dois workers concorrentes não reivindicam o mesmo evento.
2. Reclaim gera token diferente e incrementa tentativas exatamente uma vez.
3. Worker A não conclui nem falha depois que B recebeu novo token.
4. Token antigo não renova heartbeat.
5. Token correto com lease expirado não renova nem finaliza.
6. Lease expirado abaixo do teto pode ser reivindicado; no teto vai para dead_letter e não retorna.
7. Failed acima do teto nunca é reivindicado.
8. Parâmetros inválidos de lease, lote, retry e max_attempts são rejeitados.
9. Falha externa ambígua não produz duplicidade observável no adapter idempotente.
10. Interrupção do worker permite recuperação sem aceitar finalização do proprietário antigo.
11. Todos os testes com DDL usam exclusivamente PostgreSQL efêmero protegido por guarda fail-closed.
12. Mocks verificam que nenhum teste chama Google Sheets, Google Drive, Supabase remoto ou filesystem de produção.

## 9. Critérios de aceite e bloqueios

A proposta só pode avançar para runtime quando:
- SQL original/migration history de Drive e local forem reconciliados;
- o contrato de cada tabela e cada estado intermediário estiver mapeado;
- todos os consumidores concorrentes estiverem incluídos no cutover;
- testes concorrentes e de fencing passarem em banco descartável;
- nenhuma função de finalização por ID sem token permanecer ativa para o mesmo fluxo;
- grants, RLS, SECURITY DEFINER e search_path forem revisados;
- plano de rollback e observabilidade estiverem documentados.

**Bloqueio atual:** cinco arquivos SQL originais relacionados a Drive/local/privileges continuam não localizados nas referências examinadas; o código instalado e o SQL local não têm equivalência integral comprovada. Portanto, esta proposta não adiciona migration, não modifica workers e não pode ser interpretada como correção aplicada.

## 10. Limites desta entrega

Nenhuma migration, DDL/DML, consulta ou escrita em Supabase remoto, execução de função, alteração de schema, alteração de credenciais, execução de worker, chamada Sheets/Drive, alteração de workflow operacional, merge, deploy ou alteração em main foi realizada.
