# ADR-001: Notificações orientadas a eventos para as outboxes do GTI SESA

- **Status:** Proposta para implementação por gates
- **Data:** 2026-10-13
- **Escopo:** despertar os workers de sincronização; não alterar o modelo de dados do inventário
- **Decisão imediata:** manter o polling atual como mecanismo de recuperação até que o caminho por evento seja validado em ambiente isolado

## Contexto

O PostgreSQL/Supabase é a fonte oficial dos dados. As integrações com Google Drive, Google Sheets e o espelhamento local são entregues por outboxes e workers independentes. O agendamento do GitHub Actions a cada cinco minutos reduz a latência, mas ainda depende de polling, disponibilidade dos runners, rede e cotas externas.

Um evento de notificação não pode substituir a outbox: notificações podem atrasar, falhar ou ser duplicadas. A outbox persistida continua sendo a fila durável e a autoridade para decidir o que precisa ser processado.

## Decisão arquitetural proposta

Adotar **wake-up por evento + reconciliação periódica**, sem migrar de uma vez todos os workers:

1. A transação de negócio grava os dados e o evento na outbox existente.
2. Um mecanismo PostgreSQL assíncrono (a avaliar: Database Webhooks/pg_net, com segredo dedicado e mantido fora do código) emite uma notificação mínima após a inserção de um evento elegível.
3. Um endpoint de despertar autenticado solicita ao worker existente um lote limitado. O payload do webhook serve apenas como sinal; o worker volta a consultar e reivindicar eventos elegíveis no PostgreSQL. Não confiar em IDs/status enviados pelo cliente como autorização para processar.
4. O worker reivindica itens com as funções de claim já existentes, valida integridade, executa a operação externa e finaliza ou agenda retry.
5. O polling atual continua ativo como **reconciliação/fallback**. Uma notificação perdida não pode deixar um evento pendente indefinidamente.
6. O espelhamento local continua independente: a notificação remota não prova que o computador está ligado nem que o serviço local está ativo.

### Fluxo

Transação de negócio → PostgreSQL + outbox durável → notificação assíncrona (melhor esforço) → endpoint autenticado → worker reivindica lote → Drive/Sheets com verificação.

O polling de reconciliação permanece ligado em paralelo para recuperar eventos que não geraram ou não receberam a notificação.

## Requisitos de segurança e confiabilidade

- **Sem gravações externas durante deploys:** não executar workers automaticamente em resposta a push ou merge; o código implantado não deve, por si só, consumir a fila.
- **Autenticação dedicada:** segredo de notificação distinto de credenciais Google e da chave administrativa do Supabase; não incluir segredos no payload, logs, SQL versionado ou workflow.
- **Idempotência:** usar as rotinas de claim/finalização existentes e identidade estável do evento. A repetição de uma notificação deve ser segura.
- **Concorrência:** limitar lote, timeout e frequência; manter exclusão mútua por worker e usar a reivindicação atômica da outbox. Uma notificação nunca deve permitir duas reivindicações do mesmo evento.
- **Retentativas:** manter pending, proxima_tentativa_em, contador e erro rastreável. Dependências ainda não prontas são adiadas, não tratadas como falhas definitivas.
- **Reconciliação:** manter polling periódico até comprovar que o caminho de eventos é confiável; nunca depender exclusivamente de webhook.
- **Observabilidade:** registrar apenas IDs técnicos, modo, quantidade reivindicada/concluída, duração e códigos de erro sanitizados. Nunca registrar tokens, URLs com credenciais ou conteúdo de fotos.
- **Limites externos:** respeitar cotas e rate limits do Google; aplicar backoff em 429/5xx, sem loops agressivos.
- **Escopo:** não modificar abas, menus suspensos, contratos da planilha, registros patrimoniais ou arquivos do Drive como parte desta etapa arquitetural.

## Plano de rollout por gates

### Gate 0 — desenho e inventário (este documento)
Documentar a arquitetura, identificar outboxes/rotinas de claim e preservar o comportamento atual. Nenhuma alteração em produção.

### Gate 1 — contrato e testes locais
- Definir formato mínimo de notificação, autenticação e respostas.
- Testar notificações inválidas, ausentes, repetidas e fora de ordem.
- Testar lote zero/vazio, concorrência, timeout e falha do destino.
- Demonstrar que o endpoint nunca processa sem autenticação e que o webhook não recebe dados sensíveis.
- Criar testes que provem que o polling continua sendo fallback.

### Gate 2 — implementação sem ativação
- Adicionar endpoint de despertar com limite rígido e modo de validação sem gravações.
- Criar migration isolada e reversível para a notificação assíncrona, somente após confirmar extensões, permissões, função de claim e disponibilidade do segredo no projeto.
- Configurar o segredo fora do Git e impedir logs do cabeçalho.
- Nenhum trigger deve ser ativado em produção neste gate.

### Gate 3 — ambiente isolado
- Instalar trigger/endpoint em projeto de teste ou ambiente local isolado.
- Inserir um evento sintético sem dados patrimoniais reais.
- Verificar notificação, claim, finalização e repetição.
- Confirmar que desligar a notificação não interrompe o polling nem perde eventos.

### Gate 4 — canário controlado
- Ativar para uma única outbox/rota de baixo risco e com volume limitado.
- Monitorar duplicidades, falhas, latência, retries, cotas e backlog.
- Manter fallback por polling e um procedimento de desligamento imediato.

### Gate 5 — expansão
Expandir gradualmente para as demais outboxes somente após métricas e auditoria aprovadas. A integração local permanece sob seu próprio serviço/timer.

## Critérios de aceite

- Uma inserção elegível desperta o worker sem esperar a próxima janela de polling, quando os serviços estão disponíveis.
- Uma notificação duplicada não duplica efeitos externos.
- Uma notificação perdida é recuperada pelo polling.
- Nenhum evento fica preso em estado de processamento após timeout sem ser recuperável.
- Falha de Drive não impede sincronização de links já disponíveis no Sheets.
- Não há alteração na fonte oficial dos dados nem no contrato da planilha.
- Logs e respostas não revelam segredos ou conteúdo pessoal/patrimonial.

## Riscos e limitações

- Webhooks e chamadas HTTP são assíncronos e não garantem latência instantânea.
- Configuração de extensões, Vault, permissões e secrets é específica do projeto e deve ser verificada antes da migration.
- O endpoint atual do Drive worker não deve ser chamado diretamente com um payload de webhook sem adaptação explícita de autenticação e contrato.
- A mudança não deve ser declarada operacional até existir evidência de teste isolado e execução observável.

## Rollback

Desabilitar primeiro o trigger/notificação e revogar o segredo dedicado. Manter os workers e o polling existentes. Não apagar nem limpar outboxes durante rollback; deixar os workers de reconciliação processarem os eventos pendentes segundo a política vigente.
