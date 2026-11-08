# Validação segura das integrações PostgreSQL/Supabase e Google Sheets

## Validação automática sem credenciais

O workflow **GTI SESA - Integration validation** executa em pull requests e em alterações relevantes na branch `main` sem exigir secrets:

- analisa a gramática PostgreSQL de `postgresql_schema.sql`, migrations Supabase e scripts SQL legados com `pglast`;
- executa testes unitários isolados para a configuração PostgreSQL;
- testa a autenticação e os contratos de acesso ao Google Sheets com mocks, sem chamadas externas;
- executa testes do worker de outbox com chamadas simuladas.

A análise sintática não equivale a aplicar migrations em um banco PostgreSQL. Os corpos PL/pgSQL e a compatibilidade semântica precisam de uma execução local Supabase/PostgreSQL isolada. Nenhuma validação deste workflow usa `--remote` ou grava em produção.

## Validação real, somente leitura

A execução externa é manual e só roda quando o workflow é disparado na branch `main`. Em pull requests, inclusive os originados de forks, nenhuma credencial é disponibilizada.

Configure em **Settings → Secrets and variables → Actions → New repository secret**:

### PostgreSQL/Supabase

- `GTI_DB_HOST`: hostname do Transaction Pooler exibido em Connect no Supabase.
- `GTI_DB_NAME`: `postgres`.
- `GTI_DB_USER`: usuário completo `postgres.<project-ref>`.
- `GTI_DB_PASSWORD`: senha do banco.

A validação abre uma conexão TLS ao pooler, configura `default_transaction_read_only=on` na sessão e executa apenas `SELECT 1` e leitura de configuração. Não executa migrations nem DDL/DML.

### Google Sheets

- `GTI_GOOGLE_SERVICE_ACCOUNT_JSON`: JSON completo da service account.
- `GTI_GOOGLE_SPREADSHEET_ID`: somente o ID da planilha, não a URL.

Compartilhe a planilha com o e-mail `client_email` da service account. O teste consulta as abas pela Sheets API e consulta `capabilities.canEdit` / `canModifyContent` pelo Drive API para confirmar a capacidade de edição sem escrever células.

A API Google Sheets deve estar habilitada no projeto Google Cloud. O escopo usado para os dados é somente leitura; o escopo Drive é apenas de metadados. O workflow não cria, atualiza, anexa ou apaga dados.

## Interpretação dos resultados

- **Offline validation: success** — SQL externo analisado e testes unitários/mocks aprovados; não comprova conectividade remota.
- **Live validation: success** — cada integração configurada foi verificada por leitura.
- **Live validation: skipped** — faltam secrets; não significa que a integração real esteja aprovada.
- **Live validation: failure** — credenciais configuradas, mas inválidas, sem permissão ou sem conectividade.

Nunca coloque JSON de service account, senha PostgreSQL, tokens ou chaves em arquivos do repositório, logs, issues ou comentários de PR.
