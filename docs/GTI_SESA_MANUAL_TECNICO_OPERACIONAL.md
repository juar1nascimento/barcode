# GTI SESA — Manual técnico, operacional e histórico consolidado

**Versão:** 1.0  
**Data de consolidação:** 2026-10-13  
**Repositório:** [juar1nascimento/barcode](https://github.com/juar1nascimento/barcode)  
**Branch documental:** `docs/gti-sesa-operational-history-20261013`  
**Documento de referência:** continuidade técnica do sistema de inventário patrimonial GTI SESA.

> **Aviso de confiabilidade:** este manual consolida informações presentes no histórico de conversas recuperável, documentação já versionada e metadados de GitHub consultados nesta etapa. Não é uma auditoria atual de produção. Fatos relatados em conversas antigas, resultados de CI, inspeções estáticas e configurações externas são categorias diferentes e estão explicitamente distinguidos. Nenhuma credencial ou valor secreto deve ser incluído neste arquivo.

## 1. Objetivo e regras de uso

Este documento existe para que futuras sessões de desenvolvimento possam retomar o sistema sem reconstruir toda a conversa. Registra arquitetura, componentes, configurações conhecidas, permissões, evidências de testes e auditorias, alterações propostas, incidentes, riscos e próximos gates.

### 1.1 Regras obrigatórias de segurança

1. Não executar migrations, SQL de escrita, workers, sincronizações, uploads ou reprocessamentos de filas em produção sem autorização explícita e gate específico.
2. Não criar projeto Supabase de teste nem conectar à produção para executar teste local. Quando houver autorização para testes, usar PostgreSQL isolado/descartável e credenciais exclusivas de teste.
3. Não ativar o wake-up do worker Drive, não processar outbox de produção e não implantar a PR #66 até resolver a concorrência de criação de pastas descrita na Issue #67.
4. Não mesclar PRs apenas porque alguns checks passaram. Conferir checks obrigatórios, revisão, diff, branch de destino e impacto operacional.
5. Não tratar nomes de variáveis/Secrets como prova de que o segredo existe, é válido ou possui os escopos necessários.
6. Nunca registrar senhas, tokens, chaves privadas, service-role keys, refresh tokens, cookies ou conteúdo secreto.
7. Separar no painel e nos relatórios: **zero real**, **consulta indisponível**, **não configurado** e **estado desconhecido**. Erro de consulta não pode virar falsa mensagem de sucesso.
8. Manter PostgreSQL como fonte de verdade; planilhas e relatórios são destinos/visões derivadas.
9. Não inventar IDs de Drive, abas, pastas, registros, projeto ou credenciais. Não usar fallback para uma pasta raiz não confirmada.
10. Preservar scripts locais não rastreados que o operador tenha pedido explicitamente para manter, incluindo `gti-sesa-check.sh`.

### 1.2 Etiquetas de evidência usadas neste manual

- **Confirmado no código/repositório:** observável em arquivos, diffs ou metadados versionados consultados.
- **Resultado registrado:** há um resultado explícito em conversa ou metadado de execução, mas não necessariamente atual.
- **Relatado historicamente:** informado em conversa anterior, sem nova verificação nesta consolidação.
- **Pendente de confirmação:** requer evidência de serviço, ambiente ou operador.
- **Proposta/não implantado:** ideia ou alteração em PR/issue que não deve ser considerada ativa.
- **Desconhecido:** não há evidência suficiente para afirmar.

## 2. Resumo executivo do estado conhecido

| Área | Estado documentado | O que isso NÃO comprova |
|---|---|---|
| Código principal | Repositório `juar1nascimento/barcode`; aplicação Streamlit em `app.py` | Que a versão atualmente publicada corresponda à branch consultada |
| Banco | Projeto Supabase historicamente identificado como `gti-inventario`, ref `vgabxdprocwmpmhoxrgt`, PostgreSQL 17 | Estado atual do schema, migrações aplicadas, filas ou permissões |
| Planilha de inventário | Em 2026-10-12 foi relatada execução estrutural em 40 abas; cabeçalho `Código de Barras` corrigido e auditoria estrutural aprovada | Permissão de edição atual, sincronização de dados, ausência de duplicatas de linhas ou estado de hoje |
| Workers/outbox | Existem caminhos para sincronização de inventário, fotos para Sheets e fotos para Drive | Que estejam ativos, habilitados, executando ou sem pendências agora |
| Drive | Roteamento e criação de pasta de patrimônio em discussão na PR #66 | Que o código da PR esteja implantado ou que a criação seja idempotente sob concorrência |
| Migrations automáticas de outbox | PR #56 registra duas migrations; revisão estática encontrou dependência da ordem | Que a produção tenha exatamente essas versões e triggers neste momento |
| Painel de integração | `painel_integracao.py` contém monitoramento de fila de fotos para Sheets | Que consultas, indicadores e ações operacionais reflitam o schema/estado atual |
| Espelhamento local | Caminho de rede e scripts registrados historicamente | Que o caminho esteja montado, acessível ou que uma cópia recente exista |
| CI/segurança | Vários resultados históricos positivos; CodeQL em algumas execuções ficou `neutral` | Aprovação integral de todas as PRs, funcionamento em produção ou permissões externas |
| BI/Data Studio | Integração planejada/considerada | Existência, fonte, proprietário, credenciais ou atualização automática confirmados |

**Conclusão de status:** sistema em desenvolvimento com gates de integração ainda abertos. Não declarar prontidão integral para produção com base apenas no histórico ou em CI.

## 3. Arquitetura funcional

### 3.1 Fluxo lógico

1. Operador acessa a aplicação Streamlit.
2. A aplicação lê/grava dados de inventário no PostgreSQL/Supabase, conforme o fluxo da funcionalidade.
3. Alterações elegíveis devem produzir eventos em outboxes.
4. Workers consomem eventos e sincronizam destinos externos:
   - inventário → Google Sheets;
   - fotos/metadados → Google Sheets;
   - arquivos de fotos → Google Drive.
5. Um espelhamento local de segurança foi projetado para gravar arquivos de forma controlada.
6. Uma projeção analítica PostgreSQL → Google Sheets → Data Studio/Looker Studio foi discutida como objetivo, mas a configuração efetiva do relatório não está confirmada.

### 3.2 Componentes e arquivos relevantes

| Componente | Arquivo/recurso | Responsabilidade conhecida |
|---|---|---|
| Aplicação | `app.py` | Entrada Streamlit, autenticação e navegação |
| Saúde de integração | `painel_integracao.py` | Indicadores e operações da outbox de fotos para Sheets |
| Sincronizador de inventário | `sincronizador_google_sheets.py` | Leitura de PostgreSQL/outbox e espelhamento em Sheets |
| Persistência | `postgresql_persistencia.py` | Conexão/persistência PostgreSQL utilizada pela aplicação |
| Worker Drive | `supabase/functions/outbox-drive-worker/index.ts` | Processamento de eventos para Drive; a versão da PR #66 é proposta |
| Migrations | `supabase/migrations/` | Histórico versionado de mudanças SQL |
| Verificação do espelho local | `scripts/check_local_mirror.py` | Preflight/checagem do destino local, conforme histórico |
| Execução do espelho | `run_local_mirror.ps1` | Orquestração e preflight do espelhamento local, conforme histórico |
| Script local | `gti-sesa-check.sh` | Script local não rastreado relatado como preservado; não apagar nem assumir que está no Git |

Os arquivos devem ser relidos na branch e commit alvo antes de qualquer alteração. Esta tabela é um mapa de navegação, não uma garantia de que todas as implementações estejam no mesmo estado.

## 4. Ambiente, configuração e permissões

### 4.1 Supabase/PostgreSQL

- Projeto historicamente identificado: `gti-inventario`.
- Project ref: `vgabxdprocwmpmhoxrgt`.
- Região relatada: `sa-east-1`.
- PostgreSQL: versão 17 em registros de outubro; em outra sessão de 2026-10-12, o ambiente local tinha `psql 18.6` instalado.
- O host direto foi citado historicamente como `db.vgabxdprocwmpmhoxrgt.supabase.co`; para a aplicação de sync, o gate de conexão exige host de Transaction Pooler `*.pooler.supabase.com`, porta `6543`, SSL e usuário/database esperados.
- O host `aws-0-sa-east-1.pooler.supabase.com` foi informado para verificação em 2026-10-03. Um workflow falhou no passo `Validate sync configuration` com `GTI_DB_HOST inválido`; portanto não presumir que a configuração de CI foi corrigida.
- Valores de senha não devem ser documentados. Nenhuma senha foi registrada aqui.

**Variáveis referenciadas historicamente:** `GTI_DB_HOST`, `GTI_DB_PORT`, `GTI_DB_NAME`, `GTI_DB_USER` e a senha de banco correspondente. Confirmar presença e valores somente no ambiente autorizado, sem copiá-los para issues/PRs/chat.

**Limites importantes:**
- Em 2026-10-12, foi relatado que não havia credenciais/variáveis de banco definidas na sessão local.
- A inspeção estática local registrou que a base de migrations não criava todas as estruturas esperadas pelo sistema; especificamente, faltavam no esquema-base inspecionado `movimentacoes_patrimonio`, papéis `anon/authenticated/service_role` e schema `storage`. Isso sugere que reproduzir o schema completo localmente exigia um ambiente base compatível; não é prova do estado atual da produção.
- Uma tentativa de validação local isolada foi discutida, sem criar projeto Supabase nem alterar produção. A validação da migration PostgreSQL permaneceu pendente naquele registro.

### 4.2 Google Sheets

- Planilha de inventário é referida no histórico como `Tabela_Patrimonios`.
- O modelo funcional é uma aba por unidade de saúde.
- Em 2026-10-12, o usuário registrou execução real: **40 abas corrigidas**, **3 sem alteração**, **0 dados sobrescritos**. A mesma sequência registrou auditoria estrutural aprovada em **40/40 abas**, com falhas vazias, cabeçalhos obrigatórios e `Foto 1`–`Foto 10` presentes exatamente uma vez.
- O cabeçalho `Código de Barras` foi alvo explícito de padronização.
- Variável com nomes inconsistentes encontrada historicamente: `GOOGLE_SPREADSHEET_ID` versus `GOOGLE_SHEET_ID`. A execução correta depende de confirmar qual nome é canônico no código/workflow atual.
- O acesso Editor da conta de serviço à planilha **não está confirmado** neste documento. Não inferir permissão a partir da existência de uma credencial.
- O estado atual das 40 abas e dos dados não foi revalidado nesta consolidação.

**Contrato estrutural e salvaguardas relatadas em PRs:**
- Bloquear cabeçalhos canônicos duplicados/ambíguos.
- Bloquear sincronização quando abas exigirem migração estrutural ou não puderem ser classificadas.
- Manter `SHEETS_REMOVE_VALIDATIONS=false` no workflow manual, conforme proposta/registro da PR #54.
- O saneamento em modo `aplicar=False` deve ser estritamente somente leitura.
- A PR #57 propõe impedir escrita quando houver mais de uma linha para o mesmo `Nº de Patrimônio`, reler a planilha depois de atualizar/inserir e exigir correspondência exata dos seis campos antes de marcar o evento como sincronizado. A PR está aberta/não integrada segundo os metadados consultados; não considerar essas proteções implantadas sem conferir o branch e o merge.

### 4.3 Google Drive e fotos

Nomes de secrets/variáveis citados no histórico:
- `GOOGLE_DRIVE_OAUTH_CLIENT_ID`
- `GOOGLE_DRIVE_OAUTH_CLIENT_SECRET`
- `GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN`
- `GOOGLE_DRIVE_FOLDER_ID`

Flags citadas:
- `DRIVE_PROCESSING_ENABLED`
- `GTI_OUTBOX_WAKEUP_WORKER_ENABLED`
- `GTI_OUTBOX_WAKEUP_SECRET`

A presença, validade, escopos, conteúdo e valores atuais desses secrets/flags são **desconhecidos** e não devem ser inferidos.

O destino pretendido tem a forma: pasta raiz configurada → pasta exata da unidade → `Patrimônio {numero_patrimonio}`. Não usar busca global sem delimitação, fallback para raiz, nem IDs inventados.

**Bloqueio crítico:** a PR #66 propõe restaurar a criação da pasta `Patrimônio {numero}` quando ausente. A rotina de lookup seguido de create tem condição de corrida: dois eventos diferentes para o mesmo patrimônio podem consultar simultaneamente, não encontrar pasta e criar duplicatas. `FOR UPDATE SKIP LOCKED` protege a reivindicação do mesmo evento, mas não serializa eventos diferentes que apontam para o mesmo patrimônio. A Issue #67 exige coordenação durável por patrimônio/destino, verificação posterior e falha fechada em caso de duplicidade/ambiguidade. Até resolver isso, não mesclar/implantar PR #66, não ativar wake-up e não processar outbox real.

### 4.4 Streamlit e autenticação

- A aplicação foi historicamente publicada em Streamlit Community Cloud.
- O histórico indica autenticação e uma verificação administrativa que compara o usuário logado com `admin_email` obtido por `_email_config()`.
- O valor real de `admin_email`, os usuários autorizados, a presença das chaves `[supabase]` em Streamlit Secrets e a versão atualmente publicada não foram inspecionados nesta consolidação.
- Uma URL pública de aplicação foi mencionada em conversa anterior; não a trate como prova de disponibilidade atual.

### 4.5 Espelhamento local

Caminho de rede registrado:
`\\172.17.27.246\t.i\02 - SUPORTE\BACKUP\Inventário gti-sesa`

Scripts registrados:
- `scripts/check_local_mirror.py`
- `run_local_mirror.ps1`

Em registro anterior foram descritos: gravação atômica, checksum SHA-256, lock para evitar sincronizações simultâneas, manifesto de integridade e preflight. O primeiro espelhamento físico e a disponibilidade atual do caminho não foram confirmados neste gate. Não assumir que o compartilhamento esteja montado ou que a cópia seja recente.

### 4.6 BI/Data Studio

A projeção PostgreSQL → Sheets → Data Studio/Looker Studio foi planejada como fase posterior. Ainda faltam evidências sobre:
- existência e URL do relatório;
- fonte de dados e esquema;
- proprietário e permissões;
- frequência/último refresh;
- tratamento de falha ou atraso;
- correspondência com as unidades e cabeçalhos oficiais.

Não declarar o BI operacional até confirmar esses itens.

## 5. Modelo de dados e outboxes

O histórico menciona filas independentes para:
1. eventos de inventário para Sheets;
2. fotos/metadados para Sheets;
3. arquivos de fotos para Drive.

As tabelas citadas em código/histórico incluem:
- `public.patrimonios_sheets_outbox`;
- `public.patrimonio_fotos_sheets_outbox`;
- uma outbox de fotos para Drive, cujo nome exato deve ser confirmado no schema/branch alvo;
- views de saúde/reconciliação, incluindo `public.patrimonio_fotos_sheets_outbox_health` e `public.patrimonio_fotos_sheets_reconciliation`.

Não assumir que todos os objetos acima existem em produção com exatamente os mesmos nomes/colunas. Conferir a definição atual antes de qualquer SQL operacional.

### 5.1 Regras esperadas

- PostgreSQL é a fonte de verdade.
- Alterações elegíveis devem enfileirar eventos de forma transacional, evitando gravação de negócio sem evento correspondente.
- Claim de evento deve ser atômico; `FOR UPDATE SKIP LOCKED` é citado nos sincronizadores.
- Retry deve respeitar limite de tentativas, backoff e classificação de falhas.
- Marcar `synced` somente após confirmação verificável do destino; em Sheets, a PR #57 exige readback dos seis campos.
- Eventos não processáveis devem terminar em estado de falha/dead-letter e permanecer visíveis para operação.
- Reprocessar deve ser ação explícita, auditável e restrita; não resetar lotes sem inspeção.
- A idempotência precisa considerar destino lógico/registro, não apenas ID do evento.

### 5.2 Revisão estática da PR #56

Arquivos:
- `20261012213050_gti_auto_enqueue_outboxes.sql`
- `20261012213108_fix_gti_photo_outbox_trigger_routing.sql`

A leitura estática realizada em 2026-10-13 observou:
- a primeira migration define/redefine funções de enqueue e triggers para outboxes de inventário e fotos;
- na função inicial de fotos, uma ramificação que compara campos de conteúdo/armazenamento também considera `drive_file_id`, podendo direcionar para Sheets quando já existe ID de Drive;
- a segunda migration redefine `gti_enqueue_foto_outboxes()`: em INSERT, direciona para Sheets quando já existem Drive ID e URL, caso contrário para Drive; alterações de conteúdo/armazenamento enfileiram Drive; alterações de metadados do Drive enfileiram Sheets quando ID e URL existem;
- portanto, a ordem de aplicação importa.

**Estado de evidência:** revisão estática, não execução SQL. A PR #56 declara que ambas foram aplicadas em produção e cita quatro triggers e contagens de outbox, mas a alegação não foi verificada independentemente nesta etapa. A consulta de arquivos da branch `main` mostrou que as duas migrations não estavam versionadas em `main` no momento daquela inspeção; isso não prova se estão ou não aplicadas em produção. O histórico aplicado no banco e o catálogo real de triggers/funções continuam pendentes de confirmação.

Contagens que aparecem na descrição da PR #56 e são apenas **relato histórico**:
- inventário: 22 `synced` / 3 `pending`;
- fotos Sheets: 13 `synced` / 1 `pending`;
- fotos Drive: 13 `synced` / 1 `pending`.

Não usar essas contagens como estado atual.

## 6. Painel de saúde da integração

Documento relacionado: [análise do painel analítico](GTI_SESA_ANALISE_PAINEL_ANALITICO.md).

A leitura estática de `painel_integracao.py`, `app.py` e `sincronizador_google_sheets.py` registrou os seguintes riscos:

1. `_health()` lê `public.patrimonio_fotos_sheets_outbox_health` e interpreta colunas por posição; se a ordem da view mudar, os indicadores podem ser trocados sem erro explícito.
2. `_reconciliacao()` lê `public.patrimonio_fotos_sheets_reconciliation` e verifica `eventos_pendentes > 0`; pode não destacar ativos com apenas eventos falhos, embora a tela também apresente falhas.
3. `_falhas()` mostra até 20 eventos failed/dead-letter da outbox de fotos para Sheets.
4. A ação “Processar fila agora” chama `processar_fila_google_sheets(limit=25)` e pode escrever no Sheets/banco.
5. A ação “Reprocessar selecionados” altera eventos para pending e faz commit.
6. Erros de consulta podem produzir listas vazias; a UI precisa distinguir erro de consulta de fila vazia.
7. O sincronizador procura linha pelo número patrimonial e atualiza quando encontra; se não encontra, insere. Execuções concorrentes distintas podem inserir duplicatas, pois o lock do evento não é lock por patrimônio.
8. Há tratamento de retry para erros/quota/timeout HTTP citados como 429, 500, 502, 503, 504, quota e timeouts; confirmar implementação exata no commit alvo antes de reutilizar.

**Melhorias recomendadas antes de confiar no painel operacional:**
- selecionar colunas explicitamente e mapear por nome;
- mostrar status de consulta e timestamp de atualização;
- separar zero real, erro, não configurado e desconhecido;
- mostrar idade do evento pendente mais antigo, última sincronização bem-sucedida por destino e latência;
- separar claramente as três filas;
- separar visualização somente leitura das ações de processar/reprocessar;
- registrar operador, horário, quantidade e resultado para toda ação operacional;
- não exibir sucesso se a leitura de estado falhou.

Nenhuma ação de processamento foi executada nesta consolidação.

## 7. Testes, CI e auditorias — registro histórico

Esta seção registra evidências e limitações; não equivale a executar novamente os testes.

### 7.1 CI/GitHub Actions

- Em registro de 2026-10-10, a PR #45 continha a migration `20261010190000_normalize_manufacturer_inventory_count.sql`; a validação PostgreSQL ainda estava pendente e a migration foi relatada como não aplicada à produção.
- Em registros anteriores, CI reportou sucesso para pytest, inventário, auditoria, dependências e hardening. CodeQL apareceu como `neutral` por configuração de análise ausente em pelo menos uma execução.
- Em 2026-10-03, o workflow de sincronização Google Sheets falhou no gate `Validate sync configuration` devido a `GTI_DB_HOST inválido`; os workers PostgreSQL→Sheets e Fotos→Sheets não foram executados nessa execução.
- Em PR #68, a consulta de checks relatou um check de GitHub Actions concluído com sucesso, CodeQL `neutral` e estado agregado `pending`. Logo, **não havia aprovação integral** naquele registro.
- Para PR #54/#47, descrições relatam testes sintéticos para cabeçalhos ambíguos e salvaguardas sem acesso a serviços reais; status atual precisa ser consultado antes de afirmar que todos passaram.
- PRs #57, #58 e #59 descrevem proteções propostas para write/readback, executor de evento único e upload de foto de teste; são propostas em revisão e não prova de comportamento implantado.

### 7.2 Auditoria estrutural do Google Sheets — 2026-10-12

Resultado fornecido no histórico:
- 40/40 abas aprovadas estruturalmente;
- cabeçalhos obrigatórios presentes exatamente uma vez;
- `Foto 1` até `Foto 10` presentes exatamente uma vez;
- falhas: lista vazia;
- execução real de padronização: 40 abas corrigidas, 3 sem alteração, 0 dados sobrescritos.

Esses são resultados registrados na conversa; não foram repetidos nesta consolidação. Eles não provam permissão de escrita atual, ausência de duplicatas de patrimônio, sucesso da sincronização, integridade das fotos nem atualidade do relatório BI.

### 7.3 Auditoria de segurança/Storage — registro de 2026-10-05

Uma resposta histórica relatou:
- Supabase/Storage/Drive íntegros (8/8);
- outbox sem pendências;
- bucket `patrimonio-fotos` privado;
- compressão JPEG com alvo aproximado de 900 KB, abaixo do limite de 1 MB;
- RLS, filas, locks, retries e unicidade ativos;
- correção de `power(...)` e retries Sheets para 429/500/502/503/504/timeouts/quota;
- remoção de limpeza de menus do ciclo normal;
- capacidade modelada até 1.200 patrimônios em 8 horas.

**Qualificação:** estes pontos são relatos históricos e não foram revalidados aqui. Outra inspeção em 2026-10-12 registrou conflito público/privado sobre o bucket `patrimonio-fotos`. Portanto, não considerar a privacidade atual do bucket confirmada até conferir configuração real com acesso autorizado e sem expor credenciais. A estimativa de capacidade é modelagem, não teste de carga certificado.

### 7.4 Teste de upload de foto

A PR #59 propõe:
- remover ID fixo de patrimônio `2`;
- manter teste desativado por padrão;
- exigir `GTI_TEST_UPLOAD_ENABLED=true` e `GTI_TEST_PATRIMONIO_ID`;
- exigir prefixo `GTI-TESTE-`;
- validar novamente imediatamente antes do upload;
- deixar explícito que sucesso confirma apenas Storage + metadados PostgreSQL, não Drive/Sheets/espelho local.

A descrição registra que nenhum upload foi executado e nenhuma migration foi aplicada por aquela alteração. A PR era draft no registro consultado; não habilitar teste até revisão/CI e autorização específica.

### 7.5 Validação local de migrations

- Em 2026-10-12, `psql 18.6` e Docker estavam disponíveis na sessão de desenvolvimento.
- Foram relatadas 10 migrations versionadas e ausência de credenciais de banco no ambiente local.
- A reprodução local estava bloqueada por dependências de schema/base ausentes na instalação isolada.
- O usuário determinou preservar `gti-sesa-check.sh`, não conectar produção, não criar projeto Supabase e não modificar dados reais.
- A validação SQL local permaneceu pendente. Não afirmar que migration foi testada localmente ou aplicada em produção sem nova evidência.

## 8. Linha do tempo consolidada

| Data | Evento registrado | Estado/evidência |
|---|---|---|
| 2026-10-02 | Arquitetura Streamlit → PostgreSQL/Supabase e espelho local; snapshot histórico de 12 patrimônios, 6 fotos, 5 unidades, 8 setores; 8 eventos de patrimônio e 6 de foto pendentes | Relato histórico; não usar como estado atual |
| 2026-10-02 | Descritos writes atômicos, SHA-256, lock de sincronização, manifesto de integridade e preflight do espelho local | Implementação relatada; não revalidada |
| 2026-10-03 | Validação de conexão restringida a Transaction Pooler, porta 6543, SSL e usuário/database esperados | Commit citado historicamente: `6eb9d6c875c99cce1a3cc97f7ccdd8246c0e0e27` |
| 2026-10-03 | Workflow de Sheets falhou por `GTI_DB_HOST inválido`; workers não executados | Falha de configuração documentada |
| 2026-10-05 | Auditoria relatada de Storage/Drive, filas, segurança e capacidade; ajuste de ID de planilha e retries | Relato histórico; bucket posteriormente apontado com possível conflito público/privado |
| 2026-10-06 a 2026-10-09 | Trabalho em registro/rastreabilidade de fotos, worker, testes de uma foto e fluxo de inventário; solicitação de melhorias nos menus com opção “Outros Patrimônio” e entrada personalizada para campos | Requisitos registrados; status exato de implementação de cada campo deve ser conferido no código |
| 2026-10-10 | PR #45 de normalização de fabricante e contagem patrimonial; teste PostgreSQL pendente | Não aplicar em produção por inferência |
| 2026-10-12 | Auditoria estrutural Sheets: 40 abas aprovadas; cabeçalho `Código de Barras` padronizado; 0 dados sobrescritos | Resultado fornecido pelo usuário |
| 2026-10-12 | Revisão local de migrations: 10 arquivos, sem credenciais de banco na sessão, schema-base incompleto; script local preservado | Sem execução de migration |
| 2026-10-12 | PR #56 registra migrations de triggers outbox, com alegação de aplicação em produção | Alegação ainda requer reconciliação independente |
| 2026-10-12 a 2026-10-13 | PR #57 propõe write/readback seguro para Sheets; PR #58 executor de evento único; PR #59 guardas de upload de foto | Não tratar como implantadas sem merge/deploy comprovado |
| 2026-10-13 | Criados/atualizados documentos de histórico, painel analítico e gate de concorrência Drive na branch documental; PR #68 aberta | Documentação, não mudança de produção |
| 2026-10-13 | Revisão estática da PR #56 e comentário na Issue #67; risco de concorrência da PR #66 documentado | Sem SQL, testes, workers ou chamadas reais ao Drive nesta etapa |

## 9. PRs, issues e estado de integração

Os metadados consultados nesta consolidação mostram as seguintes propostas/itens relevantes. Reconsultar GitHub antes de qualquer merge, pois estados podem mudar.

| Item | Tema | Regra atual de segurança |
|---|---|---|
| [PR #68](https://github.com/juar1nascimento/barcode/pull/68) | Documentação/histórico operacional | Draft/documentação; não altera `main` |
| [PR #66](https://github.com/juar1nascimento/barcode/pull/66) | Roteamento e criação de pasta de patrimônio no Drive | Não mesclar/implantar antes de resolver concorrência |
| [Issue #67](https://github.com/juar1nascimento/barcode/issues/67) | Idempotência da pasta Drive | Gate obrigatório antes de PR #66 |
| [PR #56](https://github.com/juar1nascimento/barcode/pull/56) | Migrations de triggers outbox | Não presumir estado de produção; reconciliar histórico e catálogo |
| [PR #57](https://github.com/juar1nascimento/barcode/pull/57) | Falhar fechado em escrita Sheets não verificada | Verificar CI/diff/merge; readback dos seis campos é proposta |
| [PR #58](https://github.com/juar1nascimento/barcode/pull/58) | Executor opt-in de evento único de inventário | Draft no registro; requer CI/revisão e autorização para eventual execução |
| [PR #59](https://github.com/juar1nascimento/barcode/pull/59) | Guardas para upload de foto de teste | Nenhum upload executado; não habilitar por padrão |
| [PR #54](https://github.com/juar1nascimento/barcode/pull/54) | Proteções fail-closed para sync Sheets | Confirmar status atual e contrato real antes de merge |
| [PR #47](https://github.com/juar1nascimento/barcode/pull/47) | Cabeçalhos ambíguos e saneamento somente leitura | Conferir status/diff antes de depender da proteção |
| [PR #46](https://github.com/juar1nascimento/barcode/pull/46) | Leitura resiliente do Sheets em auditoria | Conferir status/diff antes de depender da proteção |
| [PR #45](https://github.com/juar1nascimento/barcode/pull/45) | Normalização de fabricante | Migration relatada como não aplicada; PostgreSQL test pendente no registro |

## 10. Riscos técnicos prioritários

### P0 — Antes de implantar worker Drive
- Resolver corrida de criação de pastas por patrimônio.
- Garantir coordenação durável por chave do destino, não mutex em memória.
- Reconsultar pasta exata após criação; se houver duplicidade ou ambiguidade, falhar fechado.
- Cobrir em testes isolados: pasta única existente, ausente, lookup ambíguo, falha HTTP, resposta sem ID e duas execuções concorrentes.
- Não realizar chamadas reais ao Drive nos testes; manter wake-up desativado.

### P0 — Antes de confiar em trigger/outbox de produção
- Confirmar versões realmente aplicadas no histórico de migrations do projeto correto.
- Inspecionar catálogo de triggers/funções e comparar com as duas migrations da PR #56 e com `main`.
- Verificar se os triggers de inventário e foto são os esperados, sem aplicar migrations para “corrigir” a diferença.
- Confirmar nomes/colunas reais das outboxes/views antes de consultas operacionais.
- Não resetar/reprocessar filas durante a reconciliação.

### P1 — Integridade da sincronização Sheets
- Confirmar o nome canônico do ID da planilha e o acesso Editor da conta de serviço.
- Confirmar o contrato de cabeçalhos em leitura atual, sem escrever.
- Impedir duplicidade por patrimônio e exigir readback dos campos antes de marcar `synced`.
- Proteger contra eventos diferentes concorrentes que escrevam a mesma linha/aba.
- Separar a fila de inventário das filas de fotos.

### P1 — Painel e observabilidade
- Corrigir mapeamento posicional de views para mapeamento por nome.
- Exibir erro de consulta como erro, não como fila vazia.
- Separar estados por destino, idade de pendência e última sincronização confirmada.
- Tornar ações mutáveis explícitas, com confirmação e trilha de auditoria.
- Evitar que o painel processe automaticamente eventos só por abrir a página.

### P1 — Segurança de fotos
- Resolver conflito histórico sobre privacidade do bucket `patrimonio-fotos`.
- Confirmar RLS/policies e autorização de acesso a fotos sem expor URLs/tokens.
- Separar confirmação de upload em Storage de confirmação de sincronização para Drive, Sheets e espelho local.

### P2 — Espelho local e BI
- Confirmar disponibilidade, permissões e última cópia do caminho de rede.
- Verificar manifesto/checksum e logs sem alterar dados.
- Identificar relatório BI, fonte, proprietário, permissões e última atualização.

## 11. Plano de gates sugerido

Executar apenas com autorização específica para cada gate; os itens abaixo são sequência proposta, não ações já executadas.

1. **Gate A — Reconciliação de migrations:** obter evidência de leitura do histórico aplicado e catálogo de triggers/funções; comparar com PR #56 e `main`.
2. **Gate B — Contrato de schema:** confirmar objetos, colunas, views, RLS e estado do bucket por leitura autorizada.
3. **Gate C — Conexão/segredos:** validar presença e forma dos nomes de configuração sem revelar valores; confirmar pooler, porta, SSL e acesso mínimo necessário.
4. **Gate D — Google Sheets:** leitura estrutural somente leitura; confirmar 40 abas, cabeçalhos e permissões atuais; não executar worker.
5. **Gate E — Idempotência Drive:** implementar coordenação por patrimônio, revisar diff e testar apenas com mocks/ambiente isolado.
6. **Gate F — Teste controlado de um evento:** somente depois dos gates anteriores, com patrimônio de teste explícito, ID exato de evento e autorização operacional. Não processar lote.
7. **Gate G — Verificação de readback:** confirmar resultado no destino e estado de outbox, sem confundir sucesso de um destino com sucesso de toda a cadeia.
8. **Gate H — Lote gradual:** somente após aprovação dos gates anteriores, plano de rollback e observabilidade.
9. **Gate I — BI e espelho local:** ativar/validar como consumidores derivados após estabilidade dos fluxos de origem.

## 12. Procedimento de continuidade em novas conversas

Ao retomar o trabalho, começar por:
1. Ler este manual e `GTI_SESA_HISTORICO_OPERACIONAL.md`.
2. Ler `GTI_SESA_ANALISE_PAINEL_ANALITICO.md` e `GTI_SESA_GATE_CONCORRENCIA_DRIVE.md`.
3. Conferir status atual de PR #56, #57, #58, #59, #66, #68 e Issue #67.
4. Confirmar a branch/commit de trabalho; não assumir que PR aberta está implantada.
5. Declarar o gate que será tratado e o que fica explicitamente fora de escopo.
6. Não executar testes, auditorias, consultas de produção ou ações mutáveis sem respeitar as restrições atuais do usuário.
7. Ao terminar, registrar: data, branch/commit, arquivos tocados, ferramentas/serviços consultados, ações executadas, resultados, checks, limitações e próximo gate.
8. Atualizar este documento e o histórico operacional quando houver novas evidências, mantendo valores secretos fora da documentação.

## 13. Registro da consolidação de 2026-10-13

- Escopo desta alteração: documentação no repositório.
- Fontes usadas: histórico recuperável de conversas, documento operacional já existente, análise do painel, proposta de gate Drive e metadados/descrições de PRs e Issue no GitHub.
- Ações realizadas: inspeção documental/metadata e preparação deste manual.
- Ações não realizadas: nenhuma migration/consulta SQL de produção, nenhum teste local ou CI iniciado por esta consolidação, nenhuma auditoria de serviço externo, nenhum processamento de outbox, nenhuma escrita em Google Sheets/Drive, nenhum deploy, nenhuma alteração de secrets/flags, nenhuma modificação de dados do inventário.
- Limitação: nem todas as conversas antigas e configurações externas podem ser verificadas integralmente a partir deste documento. Itens marcados como histórico ou pendente precisam de evidência atual antes de decisões operacionais.

---
**Documentos complementares**
- [Histórico operacional](GTI_SESA_HISTORICO_OPERACIONAL.md)
- [Análise do painel analítico](GTI_SESA_ANALISE_PAINEL_ANALITICO.md)
- [Gate de concorrência Drive](GTI_SESA_GATE_CONCORRENCIA_DRIVE.md)
