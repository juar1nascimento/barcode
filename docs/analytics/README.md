# GTI SESA — Camada analítica

## Fonte de verdade

O PostgreSQL/Supabase é a fonte de verdade da projeção do Almoxarifado Central SESA. As views públicas utilizadas pelo painel são:

- `public.v_projecao_almoxarifado_central`: detalhamento por meta, tipo e fabricante.
- `public.v_projecao_almoxarifado_central_resumo`: indicadores agregados da unidade.

A unidade está atualmente referenciada pelo identificador `2` no SQL da aplicação e nas views. Esse vínculo deve ser validado por consulta antes de qualquer migração ou alteração estrutural.

## Modos de execução

### Validação somente leitura

A validação deve ser iniciada pelo GitHub Actions, no workflow manual
`.github/workflows/analytics-readonly-validation.yml`. Após a incorporação
aprovada do workflow à branch padrão, abrir **Actions → GTI SESA - Analytics
read-only validation → Run workflow**. Não é necessário usar o terminal Linux.

O workflow chama internamente o worker com a opção `--dry-run`.

O modo:

1. Abre conexão PostgreSQL com as credenciais de execução.
2. Define `SET TRANSACTION READ ONLY` como primeira instrução da transação.
3. Consulta as duas views analíticas.
4. Informa a quantidade de linhas e colunas identificadas.
5. Fecha a conexão sem autenticar no Google Sheets e sem executar operações externas de escrita.

O workflow `.github/workflows/analytics-readonly-validation.yml` disponibiliza essa validação manual no GitHub Actions. Ele não é agendado.

### Publicação no Google Sheets

A execução sem `--dry-run` continua sendo o caminho de publicação e pode limpar e reescrever as abas:

- `Projecao_Almoxarifado`
- `Projecao_Almoxarifado_Resumo`

O workflow `.github/workflows/projecao-looker-sync.yml` permanece separado e agendado. Não executar esse workflow durante auditorias ou homologações somente leitura.

## Proteções

- O modo de validação não instancia cliente Google nem abre planilha.
- O snapshot precisa conter cabeçalho idêntico ao contrato e linhas com a quantidade correta de colunas antes de qualquer publicação.
- Um snapshot de detalhe sem linhas de dados é ignorado; não deve apagar um snapshot anterior.
- Testes do modo somente leitura usam conexão simulada e não dependem de credenciais ou dados patrimoniais reais.
- Alterações em views, tabelas, metas, eventos, dados, secrets ou workflows de publicação exigem revisão e autorização específica do proprietário.

## Limitações atuais

A validação de código e das views não equivale à homologação visual do Looker Studio. A conexão do Looker, credenciais da fonte, filtros, campos calculados, permissões e atualização do relatório devem ser validados separadamente, sem disparar a publicação real até autorização.
