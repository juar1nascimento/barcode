# SIGS GTI SESA — Contrato analítico Google Sheets → Looker Studio

**Estado:** proposta técnica em revisão; documentação apenas.  
**Branch:** `fix/sigs-sheets-safe-reconciliation`  
**Produção:** nenhuma planilha, base de dados, credencial ou dashboard foi alterada.

## 1. Objetivo e limites

Formalizar a camada de BI do Sistema de Inventário GTI SESA sem competir com a fonte operacional nem introduzir escrita de retorno.

- **Fonte de verdade:** PostgreSQL/Supabase.
- **Espelho operacional existente:** abas de unidade no Google Sheets, alimentadas pelo outbox.
- **Consumo analítico:** Looker Studio conectado a abas analíticas tabulares e estáveis do Google Sheets.
- **Fotos:** metadados relacionados por IDs estáveis; arquivos permanecem no Drive/Storage com permissões originais.
- **Direção permitida:** PostgreSQL → outbox → Sheets → Looker Studio. O Looker Studio é somente leitura; não grava de volta no inventário.

Não usar leitura de tela, scraping do relatório ou fórmulas manuais como mecanismo de sincronização. Não ligar um conector do Looker ao inventário antes de validar permissões, esquema e consistência.

## 2. Achados da revisão de código

1. O schema atual declara as colunas canônicas de inventário, `ID Patrimônio` e `Foto 01` até `Foto 10`. As abas operacionais são separadas por unidade. Isso é útil para operação, mas é um modelo largo para análise relacional de fotos.
2. O sincronizador de fotos grava fórmulas `HYPERLINK(URL do Drive, nome)` nas colunas de foto. Isso fornece um link clicável, não uma URL direta de imagem que o Looker Studio possa renderizar como miniatura.
3. O conector Google Sheets do Looker Studio trabalha com **uma worksheet por fonte de dados**. Portanto, conectar somente uma aba de unidade não representa automaticamente o inventário de todas as unidades.
4. A auditoria de dados previamente registrada indicou 28 patrimônios ativos, 23 fotos e zero divergências no contador PostgreSQL/origem da foto; isso **não substitui** a comparação independente, linha a linha, com todas as células atuais do Sheets.
5. O caminho atual deve continuar fail-closed: não criar abas nem normalizar cabeçalhos implicitamente durante o processamento normal do outbox. Ajustes estruturais devem ser uma operação controlada, auditada e separada.

## 3. Modelo analítico proposto

Criar, somente após aprovação e ensaio em cópia/teste, duas abas dedicadas que não sejam editadas manualmente:

### 3.1 `BI_Inventario` — uma linha por patrimônio ativo

| Campo | Tipo | Regra |
|---|---|---|
| `patrimonio_id` | texto | Chave primária estável; nunca derivar do número visível |
| `numero_patrimonio` | texto | Preservar zeros à esquerda e caracteres |
| `unidade` | texto | Nome canônico da unidade |
| `setor` | texto | Nome canônico do setor |
| `tipo_patrimonio` | texto | Categoria do bem |
| `fabricante` | texto | Texto; vazio permitido |
| `codigo_barras` | texto | Preservar zeros à esquerda |
| `data_cadastro` | data/hora | Valor tipado, não string localizada |
| `ativo` | booleano | Estado lógico vindo da fonte |
| `qtd_fotos` | inteiro | Contagem distinta por ID de foto |
| `ultima_atualizacao_origem` | data/hora | Timestamp de origem, fuso definido |
| `sincronizado_em` | data/hora | Última confirmação da exportação analítica |

Os campos `ativo`, `data_cadastro` e timestamps só devem ser publicados se forem derivados de colunas reais e documentadas do PostgreSQL. Não inventar valores nem inferir status a partir de texto livre. Se o modelo atual não fornecer um campo, excluí-lo até ser mapeado explicitamente.

### 3.2 `BI_Fotos` — uma linha por foto

| Campo | Tipo | Regra |
|---|---|---|
| `foto_id` | texto | Chave primária estável |
| `patrimonio_id` | texto | Chave estrangeira para `BI_Inventario.patrimonio_id` |
| `numero_patrimonio` | texto | Campo de exibição; não é chave |
| `unidade` | texto | Dimensão de filtro |
| `setor` | texto | Dimensão de filtro |
| `ordem` | inteiro | Ordenação da galeria |
| `nome_arquivo` | texto | Rótulo sem dados sensíveis desnecessários |
| `drive_file_id` | texto | Referência estável quando disponível |
| `drive_web_url` | URL | Link de abertura, sujeito às permissões do Drive |
| `thumbnail_url` | URL/imagem, opcional | Só publicar após validar URL direta estável, acesso autorizado e renderização no Looker |
| `status_foto` | texto controlado | Estados documentados, nunca texto livre de erro |
| `criada_em` | data/hora | Timestamp da origem |
| `sincronizado_em` | data/hora | Última confirmação do espelho |

**Importante:** a aba operacional larga `Foto 01…Foto 10` pode continuar existindo para compatibilidade. A tabela normalizada de fotos deve ser um produto analítico derivado e idempotente, não uma migração destrutiva da tabela operacional.

## 4. Contrato de sincronização

### Fluxo

1. PostgreSQL confirma o registro e grava o evento na outbox na mesma transação lógica prevista pelo sistema.
2. O worker processa o evento com chave estável e operação idempotente: atualizar o mesmo `patrimonio_id`/`foto_id`, nunca duplicar por número ou nome de arquivo.
3. A exportação analítica atualiza as abas BI em lote pequeno, preservando a ordem das colunas e sem limpar linhas desconhecidas.
4. A exportação relê a chave e os campos críticos para confirmar a gravação. Falha de confirmação deixa o evento pendente/retentável; não marcar como sincronizado apenas porque a API aceitou a requisição.
5. Looker Studio lê as abas BI. Não deve ser chamado pelo worker nem participar da confirmação de sincronização.
6. Registrar métricas de última execução, duração, linhas inseridas/atualizadas, duplicidades, divergências, falhas e atraso da fila.

### Regras de integridade

- Unicidade: `patrimonio_id` em inventário; `foto_id` em fotos.
- Referencial: cada `BI_Fotos.patrimonio_id` precisa existir em `BI_Inventario`.
- Número do patrimônio não é identificador global confiável.
- Cabeçalhos duplicados, ID ausente, aba desconhecida, chave conflitante ou diferença entre contagem lida e escrita bloqueiam a publicação e geram relatório.
- Normalização estrutural e criação de abas nunca acontecem como efeito colateral da sincronização normal.
- Fórmulas não devem ser usadas para fabricar chaves, deduplicar dados ou definir estado de sincronização.
- Dados analíticos não devem expor segredos, e-mails, tokens, conteúdo de erros internos ou URLs assinadas expirantes.

## 5. Atualização e latência

Para Google Sheets, a documentação do Looker Studio lista 15 minutos como intervalo mínimo padrão de atualização da fonte, com opções mais longas. Isso é cache/atualização de consulta, não sincronização em tempo real. Assim:

- Definir objetivo inicial de BI: dados refletidos no Sheets após confirmação do outbox; visualização do relatório em até aproximadamente 15 minutos, sujeita a cache e consulta.
- Exibir no relatório `sincronizado_em`/última atualização da fonte e, se possível, a idade do dado.
- Ter instrução de atualização manual para investigação, sem confundi-la com a confirmação do worker.
- Se a escala superar a capacidade/performance do Sheets, reavaliar BigQuery ou conexão analítica direta; não fazer migração antecipada sem medição.

## 6. Projeto do dashboard

### Página 1 — Visão executiva
- Cartões: patrimônios ativos, unidades cobertas, setores, fotos vinculadas, patrimônios sem foto, itens com pendência de sincronização e idade do dado.
- Série temporal de cadastros por dia/mês, se houver timestamp confiável.
- Distribuição por unidade e por tipo de patrimônio.
- Indicadores de qualidade: IDs ausentes/duplicados, fotos órfãs e registros divergentes.

### Página 2 — Inventário
- Tabela pesquisável: número, unidade, setor, tipo, fabricante, data, código de barras, quantidade de fotos e link para o registro.
- Filtros globais: unidade, setor, tipo, status ativo (se disponível), período de cadastro e presença de foto.
- Número/código como texto para preservar zeros à esquerda.
- Ordenação e paginação; evitar expor dados não necessários.

### Página 3 — Galeria de fotos
- Filtros: unidade, setor, tipo e número do patrimônio.
- Cada foto deve exibir miniatura, número do patrimônio, unidade/setor, ordem e link para abrir o arquivo autorizado.
- Relacionamento por `patrimonio_id`, não por número nem por correspondência aproximada de nome.
- **Limitação técnica:** a função `IMAGE()` do Looker Studio renderiza campos de imagem em tabelas; não é uma galeria livre tipo mosaico. A URL precisa ser uma URL de imagem válida e confiável. A documentação também informa que campos de imagem não são renderizados quando a fonte usa credenciais do visualizador.
- Não tornar a pasta ou bucket público para fazer a miniatura funcionar. Primeiro executar prova de conceito com arquivo de teste e permissões reais. Se imagens privadas não puderem ser renderizadas com segurança, manter no Looker uma tabela de fotos com links autorizados e oferecer uma galeria autenticada no SIGS/Streamlit, ligada a partir da dashboard.

### Página 4 — Qualidade e sincronização
- Eventos pendentes, falhos e atrasados, quando esses campos estiverem disponíveis na fonte analítica.
- Última execução, duração, processados, atualizados, falhas e divergências.
- Tabela de exceções por ID com motivo categorizado e data; não incluir stack traces ou credenciais.
- Tendência de atraso e taxa de sucesso.

### Página 5 — Detalhe do patrimônio
- Atributos completos permitidos, fotos relacionadas, histórico disponível e links de origem.
- O histórico só pode ser exibido se existir tabela/evento de histórico real; não simular versões com snapshots do relatório.

### Padrão visual
- Cabeçalho institucional “GTI SESA — Sistema de Inventário”.
- Data/hora da última atualização visível em todas as páginas.
- Cores consistentes e acessíveis, unidades nos eixos, títulos claros, filtros alinhados.
- Navegação por páginas e link para a galeria autorizada.
- Aviso de dados atrasados quando exceder o SLA definido.

## 7. Medidas e definições

- **Patrimônios ativos:** contagem distinta de `patrimonio_id` filtrada pelo campo real de status ativo.
- **Fotos vinculadas:** contagem distinta de `foto_id` com `patrimonio_id` válido.
- **Patrimônios sem foto:** patrimônios ativos cuja contagem de fotos é zero.
- **Cobertura fotográfica:** patrimônios ativos com ao menos uma foto ÷ total de patrimônios ativos × 100.
- **Taxa de sincronização:** eventos analíticos confirmados ÷ eventos elegíveis, no mesmo intervalo.
- **Atraso de sincronização:** hora atual menos a criação do evento pendente mais antigo; usar UTC internamente e exibir fuso local.
- **Divergência:** campos críticos diferentes entre fonte e espelho após normalização de tipo/valor explicitamente definida.

Não somar contagens distintas após junções de um-para-muitos sem pré-agregação: juntar inventário e fotos diretamente pode multiplicar patrimônio e inflar os KPIs.

## 8. Segurança e permissões

- Usar conta de serviço/conta proprietária mínima necessária para a sincronização; nunca incorporar credenciais no código, na planilha ou no relatório.
- Revisar separadamente quem pode ver a planilha, o relatório e os arquivos de foto. Compartilhar o relatório pode ampliar o público que enxerga os dados.
- Preferir credenciais do proprietário apenas se a política institucional autorizar e se o acesso à imagem continuar restrito. Não presumir que a credencial da fonte também autorize a imagem no navegador.
- Não usar links de download temporários nem URLs assinadas com expiração como valor persistente de `thumbnail_url`.
- Não publicar informações de localização sensível, dados pessoais ou campos administrativos que não sejam necessários ao painel.

## 9. Plano de execução por gates

**Gate A — auditoria somente leitura**
- Confirmar abas e cabeçalhos reais, IDs, duplicidades e URLs de fotos.
- Fazer comparação independente de todas as linhas do Sheets com o PostgreSQL, sem escrever.
- Produzir relatório de diferenças e decisão de bloqueio/liberação.

**Gate B — contrato analítico**
- Confirmar mapeamento campo-a-campo com o esquema real do PostgreSQL.
- Testar unicidade e referências em amostra anonimizada.
- Definir quais estados de foto e de sincronização existem realmente.

**Gate C — exportação em ambiente isolado**
- Implementar exportação idempotente para `BI_Inventario` e `BI_Fotos` em cópia/teste.
- Testar repetição do mesmo evento, evento fora de ordem, chave duplicada, aba ausente, timeout e falha de confirmação.
- Comparar contagens e hashes/campos críticos.

**Gate D — prova de conceito Looker Studio**
- Conectar somente a cópia de teste; validar tipos, agregações, filtros e atualização de 15 minutos.
- Testar miniaturas com arquivo de teste sob permissões não públicas.
- Aprovar a galeria antes de usar imagens reais.

**Gate E — homologação**
- Revisão de segurança e acesso por perfis; evidências e critérios de aceite assinados.
- Somente após autorização explícita preparar rollout controlado, com plano de reversão.

## 10. Critérios de aceite

- Zero IDs duplicados nas tabelas analíticas.
- Zero fotos órfãs.
- Totais por unidade iguais aos da fonte, após filtros equivalentes.
- Reprocessar um evento não cria duplicata.
- Falha de Sheets não marca evento como confirmado.
- Última atualização e atraso visíveis.
- Campos tipados corretamente (datas, números, booleanos e IDs como texto).
- Nenhum arquivo privado foi tornado público.
- Galeria funciona com permissões reais ou fica substituída, explicitamente, por links e página autenticada.
- Evidência de comparação linha a linha e teste de atualização anexada ao gate.

## Referências oficiais

- Looker Studio — [Conectar ao Google Sheets](https://cloud.google.com/looker/docs/studio/connect-to-google-sheets): uma fonte se conecta a uma worksheet; dados tabulares, cabeçalho único e tipos coerentes.
- Looker Studio — [Gerenciar atualização dos dados](https://docs.cloud.google.com/looker/docs/studio/manage-data-freshness): Sheets oferece intervalo de 15 minutos como mínimo padrão.
- Looker Studio — [Função IMAGE](https://cloud.google.com/looker/docs/studio/image): imagens em tabelas, requisitos de URL confiável e limitações de credenciais do visualizador.

## 11. Achado de segurança bloqueante — fotos

A revisão do código identificou um ponto que precisa de decisão explícita antes de habilitar a galeria:

- `supabase_migration_fotos_google_sheets.sql` contém `UPDATE storage.buckets SET public = true WHERE id = 'patrimonio-fotos'`.
- `sheets_outbox_worker.py` gera URLs assinadas com expiração de 24 horas e grava fórmulas `HYPERLINK/IMAGE` no Sheets. O módulo `fotos_patrimonio.py` também gera URLs assinadas de 24 horas para exibição na planilha.

**Risco:** tornar o bucket público altera o modelo de acesso dos arquivos. URLs assinadas expirantes também não são um contrato confiável de imagem permanente para um relatório analítico em cache. Não é seguro resolver a galeria abrindo o bucket inteiro ao público apenas para permitir miniaturas.

**Bloqueio deste gate:** não aplicar nem reaplicar a migration, não alterar o bucket, não gerar links públicos e não publicar URLs de fotos reais no Looker Studio. Primeiro confirmar a classificação institucional das fotos e revisar o estado atual do bucket com acesso somente leitura.

**Alternativa preferida:** manter o Storage privado e, se a miniatura autenticada não puder ser consumida com segurança pelo Looker Studio, apresentar os metadados e links autorizados no relatório e abrir a galeria no SIGS autenticado. Qualquer proxy de miniaturas deve validar a sessão e autorização por arquivo, ter limites de requisição e não expor tokens na URL persistida.

Esse achado não prova que o bucket de produção esteja público agora; prova que o arquivo de migration versionado contém uma instrução para torná-lo público. O estado real de produção ainda precisa ser verificado separadamente, em modo somente leitura.
