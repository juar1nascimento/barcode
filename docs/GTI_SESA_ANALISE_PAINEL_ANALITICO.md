# GTI SESA — Análise funcional do painel analítico

**Data da inspeção de código:** 2026-10-13  
**Branch documental:** `docs/gti-sesa-operational-history-20261013`  
**Escopo:** leitura estática de `app.py`, `painel_integracao.py` e `sincronizador_google_sheets.py`. Nenhum teste, auditoria, acesso a serviço externo ou processamento de fila foi executado nesta etapa.

## 1. O que a tela analítica faz no código atual

Arquivo principal: [painel_integracao.py](../painel_integracao.py)

A página é intitulada **“Saúde da integração de fotografias”** e descreve o monitoramento da fila Supabase → Google Sheets. Ela consulta o PostgreSQL usando `postgresql_persistencia.conectar()`.

### Indicadores apresentados
A função `_health()` executa `SELECT * FROM public.patrimonio_fotos_sheets_outbox_health`. A tela interpreta os índices retornados como:
1. Pendentes;
2. Processando;
3. Sincronizados;
4. Falhos;
5. Dead-letter;
6. Prontos para retry;
7. Última sincronização (índice 7, se existir);
8. Último erro (índice 8, se existir).

**Risco de contrato:** a tela usa índices posicionais, não nomes de colunas. A ordem da view deve coincidir exatamente com o esperado pelo painel. Sem consultar a definição real da view, não se pode certificar que os indicadores estejam mapeados corretamente.

### Reconciliação
A função `_reconciliacao()` consulta `public.patrimonio_fotos_sheets_reconciliation` para patrimônios com fotos no PostgreSQL e eventos pendentes, trazendo contagens de fotos, eventos pendentes e eventos falhos. O filtro SQL atual considera `eventos_pendentes > 0`; isso pode não incluir patrimônios com somente eventos falhos, apesar de a coluna de falhas ser exibida.

### Falhas
A função `_falhas()` lista até 20 registros `failed` ou `dead_letter` da tabela `public.patrimonio_fotos_sheets_outbox`, incluindo tentativas, próxima tentativa, último erro e atualização.

### Ações com efeito real
A tela não é somente leitura:
- **“Processar fila agora”** chama `processar_fila_google_sheets(limit=25)`. Isso pode consumir eventos e escrever no Google Sheets, além de atualizar status no PostgreSQL.
- **“Reprocessar selecionados”** atualiza diretamente registros da outbox para `pending`, limpa erro e timestamp de processamento e define nova tentativa para agora, com `COMMIT`.
- A mensagem “Nenhuma falha pendente” é exibida quando a consulta de falhas retorna lista vazia. Como a exceção também é capturada e convertida em lista vazia, há risco de a tela mostrar sucesso após uma falha de consulta; embora o caminho da exceção emite `st.warning`, a mensagem de sucesso ainda pode aparecer em seguida.

**Implicação operacional:** não acionar esses botões durante a coleta passiva do estado de produção. Uma futura melhoria pode separar claramente “consultar” de “executar/reprocessar”, exigir confirmação explícita e mostrar estado de consulta indisponível como desconhecido, não como zero/sem falhas.

## 2. Controle de acesso no Streamlit

Arquivo: [app.py](../app.py)

- O login é obrigatório antes do roteamento.
- A condição administrativa compara o usuário logado com `admin_email` obtido por `_email_config()`.
- As páginas de auditoria pré-migração, preflight Supabase, teste de upload e saúde da integração verificam `is_admin` novamente antes de renderizar.
- Ocultar o menu nativo do Streamlit é apenas apresentação; a proteção real depende das verificações de autorização no roteamento.
- A regra atual parece ser uma comparação com um único e-mail de administrador, não um sistema granular de papéis. A configuração efetiva de `admin_email` no Streamlit Secrets não foi lida nesta inspeção.

## 3. Sincronizador e contrato de dados

Arquivo: [sincronizador_google_sheets.py](../sincronizador_google_sheets.py)

- Usa PostgreSQL como fonte operacional e outboxes como fila de espelhamento.
- `_claim()` utiliza transação e `FOR UPDATE SKIP LOCKED` para evitar que consumidores reivindiquem o mesmo evento de outbox ao mesmo tempo.
- A reivindicação por evento não evita necessariamente que dois eventos diferentes do mesmo patrimônio sejam processados em paralelo.
- `_espelhar_patrimonio()` procura a linha pelo número do patrimônio e atualiza a linha existente; se não encontrar, acrescenta uma linha. Duas execuções concorrentes para o mesmo patrimônio podem exigir proteção adicional contra append duplicado.
- Há um helper `_remover_validacoes_menu_suspenso()` que executa escrita no Sheets. A existência do helper não prova que seja chamado no fluxo atual. O histórico do PR #54 relata a proteção para manter `SHEETS_REMOVE_VALIDATIONS=false` no workflow manual e evitar essa ação no ciclo normal; o estado atual dos workflows/flags deve ser confirmado antes de execução.
- As chamadas de Sheets têm retries para 429, 500, 502, 503, 504, quota e timeout.
- O sincronizador importa funções para garantir cabeçalhos/coluna de patrimônio e valida o cabeçalho canônico antes de escrever; alterações estruturais devem continuar bloqueadas no consumidor normal.
- Para fotos, o sincronizador consulta metadados PostgreSQL e campos `drive_file_id`, `drive_folder_id`, `drive_web_url`; a análise completa do caminho de fotos exige ler o restante do módulo e a view/outbox reais.

## 4. Lacunas que impedem declarar a análise “operacional confirmada”

Não foram confirmados por leitura do ambiente real:
- Definição/ordem das colunas de `patrimonio_fotos_sheets_outbox_health`;
- Definição atual de `patrimonio_fotos_sheets_reconciliation`;
- Contagens e idade dos eventos atuais;
- Se os workflows programados estão habilitados e qual foi a última execução bem-sucedida;
- Se a conexão PostgreSQL do Streamlit Cloud está válida;
- Se a conta de serviço tem permissão Editor na planilha;
- Se a planilha, suas 40 abas e os cabeçalhos atuais ainda atendem ao contrato;
- Se o dashboard Data Studio está conectado à fonte correta e quando atualizou pela última vez;
- Se a cópia local e seu timer estão ativos.

## 5. Plano de desenvolvimento sem executar testes/auditoria agora

1. Registrar o contrato esperado da view de saúde com nomes de colunas, não apenas índices.
2. Separar visualmente os estados `0`, `consulta indisponível` e `não configurado`.
3. Corrigir o estado da consulta de falhas para não permitir mensagem positiva após erro de leitura.
4. Mostrar idade do evento pendente mais antigo, duração/latência de sincronização, último sucesso por destino e totais de falha/retry.
5. Exibir contagens distintas para outbox de patrimônio, fotos Sheets e fotos Drive; não misturar eventos de destinos diferentes.
6. Separar reconciliação de dados de ações operacionais; as ações de processar/reprocessar devem ser explícitas, limitadas e registrar operador/horário/resultado.
7. Antes de qualquer execução real, confirmar permissão da planilha e estado dos workflows por consulta somente leitura.
8. Só depois, planejar uma validação isolada e uma mudança por PR; não executar automaticamente por esta documentação.

## Conclusão

O painel já possui uma base operacional útil para observar a fila de fotos do Google Sheets, falhas e reconciliação, mas também contém botões que produzem efeitos reais. A tela não deve ser tratada como dashboard puramente analítico. A ordem posicional da view de saúde, o tratamento de consulta indisponível e a concorrência entre eventos do mesmo patrimônio são pontos importantes para a próxima evolução. Nenhum teste, auditoria, processamento ou escrita em serviço externo foi realizado durante esta análise.
