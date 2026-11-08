# Validação segura das integrações PostgreSQL/Supabase e Google Sheets

## Validação automática sem credenciais

O workflow **GTI SESA - Integration validation** executa em pull requests e em alterações relevantes na branch `main` sem exigir secrets:

- analisa a gramática PostgreSQL de `postgresql_schema.sql`, migrations Supabase e scripts SQL legados com `pglast`;
- executa testes unitários isolados para a configuração PostgreSQL;
- testa a autenticação e os contratos de acesso ao Google Sheets com mocks, sem chamadas externas;
- executa testes do worker de outbox com chamadas simuladas.

A análise sintática não equivale a aplicar migrations em um banco PostgreSQL. Os corpos PL/pgSQL e a compatibilidade semântica precisam de uma execução local Supabase/PostgreSQL isolada. Nenhuma validação deste workflow usa `--remote` ou grava em produção.

A documentação e o changelog Supabase foram revisados em 8 de novembro de 2026. O Supabase CLI v3 mudou a seleção de destino: comandos de banco usam o stack local por padrão, enquanto operações hospedadas exigem `--remote` e, em CI, consentimento explícito `--yes`. A nova configuração local deve usar as chaves atuais (por exemplo, `[local_smtp]`, não a antiga `[inbucket]`). Este PR não instala nem executa a CLI; quando o baseline for reconstruído, a versão da CLI deverá ser fixada e o workflow deverá limitar-se ao stack descartável local.

### Lacuna encontrada no baseline atual

A inspeção do schema e de todos os SQL versionados identificou pré-requisitos ausentes para reconstruir um banco limpo: não há declaração versionada para `public.movimentacoes_patrimonio`, `public.patrimonio_fotos_sheets_outbox` nem para a view `public.patrimonios_sheets_outbox_health`; também não existe `supabase/config.toml`. O validador sinaliza essas lacunas como **BLOCKED_BY_BASELINE_GAPS**.

Esses objetos podem existir no banco remoto atual, mas não estão descritos integralmente no baseline versionado que foi auditado. Não criei tabelas ou views presumindo colunas, constraints, índices ou políticas. A próxima etapa correta é recuperar/confirmar o DDL canônico do ambiente autorizado e transformá-lo em baseline/migrations reproduzíveis antes de habilitar um teste `supabase start` + `supabase db reset` em banco descartável.

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
