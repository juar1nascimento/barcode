# GTI SESA — Histórico operacional e mapa de configurações

**Registro iniciado:** 2026-10-13  
**Objetivo:** referência persistente para próximas conversas e mudanças no projeto, sem depender da memória do chat.  
**Escopo:** registrar apenas fatos encontrados no histórico de conversas e em metadados/código do repositório. Este documento não é uma certificação de produção.

## Regras para uso deste histórico

- Nunca armazenar tokens, senhas, chaves privadas, service-role keys, refresh tokens, cookies ou valores secretos.
- Um nome de secret/environment variable não prova que o valor existe, é válido ou tem permissão suficiente.
- Distinguir sempre: **configurado e confirmado**, **registrado no código**, **relatado anteriormente**, **pendente de confirmação** e **não conhecido**.
- CI verde valida somente os checks executados; não comprova permissão real de Google Drive/Sheets, execução de worker, sincronização ou configuração do Streamlit Cloud.
- Não aplicar migrations, não disparar workers de produção, não alterar planilhas/arquivos reais e não implantar Edge Functions sem um gate específico.
- Preservar `main`; fazer mudanças em branches isoladas e PRs. Não mesclar PRs só porque foram criados.
- Para segredos, consultar apenas presença/nomes/estado por interfaces autorizadas. Nunca copiar valores para issues, PRs, logs ou este arquivo.

## Arquitetura conhecida

1. **Aplicação:** Streamlit, repositório `juar1nascimento/barcode`, entrypoint `app.py`; aplicação publicada anteriormente em Streamlit Community Cloud.
2. **Persistência principal:** Supabase/PostgreSQL. O projeto identificado no histórico é `gti-inventario`, ref `vgabxdprocwmpmhoxrgt`, PostgreSQL 17.
3. **Fotos:** Supabase Storage, bucket `patrimonio-fotos`; metadados em `public.patrimonio_fotos`. O desenho mais recente usa Storage privado e links do Drive na sincronização; houve uma configuração histórica conflitante de bucket público para fórmulas IMAGE do Sheets. Confirmar o estado atual antes de qualquer alteração.
4. **Sincronização:** outboxes para inventário, fotos/Google Sheets e fotos/Drive; funções/workers com retries e estados; migrations de triggers automáticos registradas em PR #56.
5. **Google Sheets:** planilha de inventário com abas por unidade. Contrato recente inclui colunas canônicas e a coluna opcional `Código de Barras`; não modificar cabeçalhos/validações no ciclo normal do worker.
6. **Google Drive:** worker `supabase/functions/outbox-drive-worker/index.ts`; rota esperada é raiz configurada → pasta exata da unidade → `Patrimônio {numero_patrimonio}`. Nunca inventar IDs nem usar fallback de raiz.
7. **Espelhamento local:** destino histórico informado: `\\\\172.17.27.246\\t.i\\02 - SUPORTE\\BACKUP\\Inventário gti-sesa`. Existe/foi criado preflight `scripts/check_local_mirror.py` e instalador `run_local_mirror.ps1`. O primeiro espelhamento físico não foi confirmado; timer local não pode ser considerado instalado/atualizado só pelo código do instalador.
8. **Analytics/saúde:** `app.py` importa `painel_integracao.py` e oferece a página administrativa “Saúde da sincronização”; também há tela de auditoria pré-migração e preflight de secrets Supabase. A existência da tela não comprova que todos os indicadores estejam operacionais ou que fontes externas estejam atualizadas.
9. **Relatórios/Data Studio:** integração/projeção PostgreSQL → Sheets → Data Studio foi planejada no histórico; estado atual da conexão, atualização automática, credenciais e painéis publicados não foi confirmado nesta inspeção.

## Configurações e permissões — mapa sem valores secretos

| Área | Evidência disponível | Estado para decisões futuras |
|---|---|---|
| GitHub Actions / CI | Há PRs e workflows de CI, testes Python, auditoria e segurança mencionados no histórico | Confirmar checks do PR e branch atual antes de cada merge |
| GitHub secrets para PostgreSQL | Workflow histórico espera `GTI_DB_HOST` como hostname do Transaction Pooler, porta 6543, SSL; `GTI_DB_NAME=postgres`; usuário no formato `postgres.vgabxdprocwmpmhoxrgt`; senha em secret | Presença/validade/permissões atuais não confirmadas; não imprimir valores |
| Supabase | Projeto `gti-inventario`, ref `vgabxdprocwmpmhoxrgt`; Supabase URL conhecida pelo formato do projeto | Não tratar como prova de acesso à conta nem de permissões atuais |
| Supabase migrations | Histórico menciona 10 migrations ordenadas no repositório em 2026-10-12; schema base não continha algumas tabelas/views/outboxes esperadas na auditoria local | Conferir histórico de migrations e catálogo antes de qualquer migration; nenhuma replay automática |
| Triggers/outboxes | PR #56 registra duas migrations aplicadas e verificadas em produção em 2026-10-12: `20261012213050_gti_auto_enqueue_outboxes.sql` e `20261012213108_fix_gti_photo_outbox_trigger_routing.sql` | Histórico do PR afirma aplicação; reconfirmar estado apenas por leitura autorizada quando necessário |
| Contagens outbox | Snapshot registrado em PR #56: inventário 22 synced/3 pending; fotos Sheets 13 synced/1 pending; fotos Drive 13 synced/1 pending | São contagens históricas, não números atuais |
| Google OAuth / Drive | Worker lê `GOOGLE_DRIVE_OAUTH_CLIENT_ID`, `GOOGLE_DRIVE_OAUTH_CLIENT_SECRET`, `GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN`, `GOOGLE_DRIVE_FOLDER_ID` | Os nomes estão no código; presença, validade e escopo OAuth atuais não confirmados |
| Flags do worker | Código contém `DRIVE_PROCESSING_ENABLED`, `GTI_OUTBOX_WAKEUP_WORKER_ENABLED`, `GTI_OUTBOX_WAKEUP_SECRET`; wake-up protegido por segredo e flag | PR #66 diz que flags não foram alteradas; estado real atual precisa ser consultado antes de habilitar |
| Google Sheets | Histórico cita correção da divergência `GOOGLE_SPREADSHEET_ID` vs `GOOGLE_SHEET_ID`; conta de serviço precisa de acesso Editor à planilha | O nome canônico efetivamente usado e o compartilhamento atual precisam de confirmação. Não assumir permissão Editor só por configuração no código |
| Streamlit Secrets | `app.py` tem preflight de secrets e menciona `[supabase]` com URL e chave secreta | Código mostra como verificar; não comprova que as secrets estejam presentes no app publicado |
| Bucket de fotos | Histórico contém conflito entre configuração pública legada e hardening privado | Estado atual do bucket precisa de leitura autorizada; não alternar público/privado sem avaliar links e política de acesso |
| Servidor/espelhamento local | Caminho UNC e scripts de preflight/instalação documentados no histórico | Acesso de rede, credenciais, timer e primeiro espelhamento não confirmados como concluídos |
| Data Studio / BI | Integração foi planejada | Projeto, fonte de dados, conta proprietária, permissões, atualização e painéis não confirmados |
| Permissões humanas/serviços | Histórico menciona conta de serviço Sheets e service role Supabase | Não há inventário confiável de pessoas/grupos, compartilhamentos ou escopos OAuth; coletar estado sem revelar credenciais |

## Linha do tempo resumida

### 2026-10-02 — arquitetura e espelhamento local
- Arquitetura relatada: Supabase/PostgreSQL como fonte, Streamlit como interface, fotos/metadados no Storage/PostgreSQL e cópia local.
- Planilha XLSX de referência com cinco colunas canônicas.
- Foi relatado que o caminho UNC estava acessível, mas o primeiro espelhamento físico ainda não estava concluído.
- Criado preflight `scripts/check_local_mirror.py` e gate de execução `run_local_mirror.ps1`.

### 2026-10-03 — acesso PostgreSQL em GitHub Actions
- Configuração esperada do Transaction Pooler: hostname `*.pooler.supabase.com`, porta 6543, SSL, banco `postgres`, usuário `postgres.<project-ref>`.
- Um teste anterior falhou antes de executar workers porque `GTI_DB_HOST` estava inválido; checks de CI/Python/auditoria/CodeQL foram relatados como aprovados. Isso não comprova que o problema de conexão foi corrigido depois.

### 2026-10-05 — sincronização e fotos
- Histórico relata 8/8 fotos íntegras/sincronizadas em uma execução anterior, Storage privado, SHA-256, retries e outbox com `SKIP LOCKED`.
- Foi corrigida uma divergência de nome do secret/variável de ID da planilha.
- Outro registro menciona execução de Sheets #37379302474 e commit `be43f21...`; a liberação geral de produção permaneceu bloqueada por gates pendentes.
- Esses resultados são snapshots históricos, não uma garantia do estado de hoje.

### 2026-10-10 — migration isolada
- PR #45 contém `20261010190000_normalize_manufacturer_inventory_count.sql`.
- Histórico informa que CI passou, CodeQL ficou neutral e validação PostgreSQL permanecia pendente.
- Restrição explícita: preparar teste local isolado sem criar projeto Supabase e sem alterar produção.
- A migration não deve ser considerada aplicada com base apenas no PR.

### 2026-10-12 — schema, outboxes e planilha
- Auditoria local identificou divergência entre schema base e objetos esperados; sem PostgreSQL local pronto para replay e sem variáveis de conexão; nenhuma migration foi executada nessa tentativa.
- PR #56 documenta duas migrations de triggers de outbox que o histórico afirma terem sido aplicadas e verificadas em produção em 2026-10-12.
- Em `Tabela_Patrimonios`, foi relatado que 40 abas receberam `Código de Barras`, 3 não precisaram de alteração e nenhum dado foi sobrescrito.
- PR #57 (rascunho, não mesclado segundo o histórico) adiciona readback, bloqueio de patrimônio duplicado e reprocessamento de falhas. O gate de produção ainda dependia de um evento isolado, confirmação da permissão da planilha, releitura da linha e confirmação de PostgreSQL/outbox em `synced`.

### 2026-10-13 — worker Drive e concorrência
- PR #66: [fix: preserve deployed Drive patrimônio-folder routing](https://github.com/juar1nascimento/barcode/pull/66).
- O corpo do PR relata inspeção read-only da Edge Function implantada `outbox-drive-worker` versão 22: comportamento implantado cria a pasta filha exata `Patrimônio {numero}` quando ausente; `main` falhava fechado nesse cenário.
- O patch encontrado adiciona `ensurePatrimonioFolder`: pesquisa a pasta e, se ausente, faz POST para criá-la. Isso resolve o caso de pasta ausente, mas **não é atômico**: duas execuções podem ambas obter “ausente” e criar duas pastas.
- O código do worker já usa claim transacional do outbox, verifica SHA-256, procura arquivo por `gti_outbox_id` e finaliza o evento. Claim por evento não garante exclusão mútua entre eventos diferentes que apontem para o mesmo patrimônio/pasta.
- O PR relata que não houve deploy, alteração de secrets/flags, alteração de banco nem processamento do outbox. CI e revisão são gates anteriores a qualquer deploy.
- Próxima correção: coordenação compartilhada por chave lógica da pasta, com recuperação de lease e idempotência. Não confiar apenas em lock local ou no padrão “pesquisar e depois criar”.

## Situação analítica e de observabilidade

### Componentes confirmados no código
- `app.py` usa layout Streamlit wide e login obrigatório.
- O acesso às telas de Administração depende de `usuario_logado` coincidir com `admin_email` configurado por `_email_config()`.
- Páginas administrativas: “Auditoria pré-migração”, “Preflight Supabase”, “Teste upload de foto” e “Saúde da sincronização”.
- `painel_integracao.py` é o módulo da tela de saúde; sua disponibilidade no código não certifica as consultas, métricas ou atualidade dos dados.
- A página de preflight menciona a verificação das secrets Supabase e oferece uma consulta de leitura ao Storage, explicitamente sem criar/enviar/alterar/excluir arquivos.

### Métricas/dashboards ainda não comprovados como ativos
- Frescor e completude das projeções Sheets/Data Studio.
- Latência real entre gravação, outbox, Drive, Sheets e espelho local.
- Taxa atual de eventos `pending/processing/failed/synced`, tentativas, idade do evento mais antigo e discrepâncias entre foto, Storage, Drive e planilha.
- Execução atual dos workflows agendados e do timer do computador local.
- Acesso atual do usuário administrador e compartilhamento da planilha com a conta de serviço.
- Não executar teste de carga nem processamento real para preencher lacunas de observabilidade sem gate autorizado.

## Backlog de próximos gates (sem executar testes ou auditorias nesta etapa)

1. **Concorrência Drive:** desenhar e revisar mecanismo de lock/lease compartilhado por chave da pasta; incluir expiração e recuperação segura após interrupção; garantir que não se use somente lock em memória.
2. **Fonte de verdade:** verificar por leitura o estado de PR #66, branch e checks; não mesclar ou implantar sem aprovação explícita.
3. **Inventário de configurações:** consultar apenas nomes/presença/flags e permissões efetivas, sem imprimir valores secretos.
4. **Painel analítico:** ler `painel_integracao.py` e os contratos de outbox para documentar definição, origem e limitações de cada indicador; separar métricas de código das métricas confirmadas em produção.
5. **Sheets:** confirmar o ID/secret canônico e o acesso Editor da conta de serviço sem fazer escrita.
6. **Supabase:** comparar migrations do repositório com o histórico aplicado e o catálogo somente leitura antes de qualquer mudança de schema.
7. **BI/Data Studio:** identificar relatório, fonte de dados, proprietário e última atualização antes de declarar a integração operacional.
8. **Espelhamento local:** confirmar instalação e estado do timer, caminho e credenciais por preflight somente leitura; não iniciar cópia até o gate específico.
9. **Registro contínuo:** atualizar este arquivo em PRs posteriores com data, evidência, estado anterior/novo e rollback; nunca registrar segredo.

## Estado inicial deste documento

Este arquivo consolida informações recuperadas do histórico do ChatGPT e inspeções pontuais do GitHub em 2026-10-13. Ele não foi construído por uma auditoria completa dos serviços externos. Onde o estado real não foi consultado nesta sessão, está explicitamente marcado como pendente/não confirmado.
