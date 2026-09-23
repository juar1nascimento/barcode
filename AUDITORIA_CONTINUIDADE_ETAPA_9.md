# AUDITORIA DE CONTINUIDADE — ETAPA 9

Data: 10/09/2026
Repositório: `juar1nascimento/barcode`
Branch-base auditada: `main`
Commit-base atual: `f69cf253fcc36baabb2980fcd7155393d73d778f`

## 1. Objetivo desta auditoria

Reconstituir as decisões e o estado técnico dos últimos trabalhos antes de iniciar a evolução para PostgreSQL, evitando repetir alterações, partir de uma branch antiga ou incorporar inadvertidamente mudanças que ainda não foram validadas/mescladas.

## 2. Histórico consolidado

### Etapas de inventário já consolidadas na main

- Organização dos menus/listas de Setores, Patrimônios e Fabricantes.
- Saneamento das opções legadas/duplicadas e manutenção do schema moderno.
- Regra de integridade: `Nº de Patrimônio` é identificador único global.
- Padronização de data/hora do cadastro para `DD-MM-YYYY HH:MM:SS`.
- Auditoria estrutural da planilha histórica.
- Registro da Etapa 8 no commit `f69cf253fcc36baabb2980fcd7155393d73d778f`.

### Evidência da Etapa 8

A auditoria registrada informa 40 abas, 29 vazias, 11 com dados e 56 linhas físicas na cópia analisada. Também registra cabeçalhos históricos diferentes, duplicidade de grafia em nomes de unidades e ausência de `Data Cadastro` preenchida na cópia. O identificador do scanner passou a ser tratado como identificador único global do patrimônio. A cópia histórica já não continha `Código de Barras`, `Origem` e `Status` no schema moderno.

## 3. Trabalhos recentes ainda NÃO consolidados na main

Existem PRs abertas em estado draft:

- PR #10 — `correcao-auditoria-funcional`: adiciona camada de movimentação persistente para Entrada/Saída. Ainda não foi mesclada.
- PR #12 — `auditoria-estabilidade-2026-09`: adiciona correções/testes de regressão. Ainda não foi mesclada.
- PR #13 — `audit/postgresql-architecture`: auditoria arquitetural PostgreSQL, criada anteriormente. Ainda é draft.

Conclusão: a base segura para a evolução PostgreSQL continua sendo a `main`, não as branches das PRs #10 ou #12, porque elas não estão consolidadas na linha principal.

## 4. Estado da persistência atual

O inventário ainda utiliza Google Sheets como persistência principal e XLSX local como apoio/backup no fluxo atual. O PostgreSQL ainda NÃO foi integrado ao código da `main`.

Portanto, não há sincronização GitHub ↔ PostgreSQL implementada neste momento.

A estratégia correta permanece:

`GitHub = código + migrações + testes`

`PostgreSQL = dados operacionais`

`Aplicação = camada que acessa o PostgreSQL`

## 5. Dependências atuais

`requirements.txt` da `main` contém `duckdb`, `gspread`, `gspread-dataframe`, `gspread-formatting`, `gspread-pandas`, `openpyxl`, `pandas`, `streamlit` e `st-gsheets-connection`, entre outras. Não há ainda `SQLAlchemy`, `psycopg` ou `alembic` declarados nesse arquivo.

Isso confirma que a integração PostgreSQL ainda deve ser uma etapa futura e controlada.

## 6. Decisões que devem ser preservadas

1. Não alterar a `main` diretamente para iniciar a migração.
2. Não apagar o Google Sheets durante a migração.
3. Não importar dados históricos antes de fazer auditoria/normalização/deduplicação.
4. Não usar o usuário PostgreSQL `postgres` como usuário da aplicação.
5. Não versionar senha, URL com senha ou `secrets.toml`.
6. Garantir unicidade do patrimônio no próprio PostgreSQL por constraint/index UNIQUE.
7. Usar transações para operações de cadastro e movimentação.
8. Manter o identificador de patrimônio globalmente único.
9. Preservar o schema canônico de cinco campos do inventário.
10. Separar estado atual do patrimônio e histórico de movimentações.

## 7. Arquitetura-alvo

```text
Streamlit UI
    |
    v
Serviços / regras de negócio
    |
    v
Repositórios
    |
    v
SQLAlchemy + psycopg 3
    |
    v
PostgreSQL
```

O acesso ao banco não deve ser espalhado pelas telas Streamlit.

## 8. Modelo inicial recomendado

Entidades:

- `unidades`
- `setores`
- `tipos_patrimonio`
- `fabricantes`
- `patrimonios`
- `movimentacoes`

A tabela `patrimonios` terá uma chave técnica `id` e `numero_patrimonio` UNIQUE. Chaves estrangeiras ligarão patrimônio à unidade, setor, tipo e fabricante.

## 9. Sequência de continuidade

### ETAPA 9A — preparação local

1. Identificar o sistema operacional do computador.
2. Instalar PostgreSQL 18.
3. Validar serviço e `psql`.
4. Criar banco `gti_inventario`.
5. Criar usuário `inventario_app` com senha forte.
6. Testar conexão local.

### ETAPA 9B — estrutura de banco

1. Criar migrações.
2. Criar tabelas e constraints.
3. Criar índices.
4. Inserir os tipos oficiais.
5. Validar integridade.

### ETAPA 9C — camada Python

1. Adicionar `SQLAlchemy`.
2. Adicionar `psycopg` 3.
3. Adicionar `Alembic`.
4. Criar módulo de conexão.
5. Criar repositórios.
6. Criar testes isolados de PostgreSQL.

### ETAPA 9D — migração de dados

1. Fazer cópia dos dados atuais.
2. Normalizar cabeçalhos históricos.
3. Consolidar nomes de unidades.
4. Deduplicar por `Nº de Patrimônio`.
5. Validar registros sem setor/tipo/unidade.
6. Importar.
7. Comparar contagens e registros.

### ETAPA 9E — troca controlada da persistência

1. Alterar leitura para PostgreSQL.
2. Alterar cadastro para PostgreSQL.
3. Alterar exclusão para PostgreSQL.
4. Implementar movimentações transacionais.
5. Testar concorrência.
6. Manter Google Sheets apenas como referência durante a validação.

### ETAPA 9F — produção

O PostgreSQL local será usado no desenvolvimento. Para Streamlit Cloud, será necessário um PostgreSQL acessível pelo ambiente de produção, com TLS/SSL e credenciais em Secrets. Não será aberto o PostgreSQL residencial diretamente à internet.

## 10. Próximo passo seguro definido

O próximo passo não é alterar o código do inventário.

O próximo passo é **auditar o ambiente local e instalar/validar o PostgreSQL**, depois criar o banco vazio. Somente após o banco responder corretamente será criada a primeira migration e o módulo de conexão.

## 11. Critério para considerar a etapa concluída

A etapa de preparação será considerada concluída somente quando:

- PostgreSQL estiver instalado;
- serviço estiver ativo;
- banco `gti_inventario` existir;
- usuário `inventario_app` conseguir conectar;
- aplicação Python conseguir executar `SELECT version()`;
- nenhum segredo tiver sido enviado ao GitHub.

## 12. Conclusão

A auditoria confirma continuidade direta: o projeto não deve recomeçar a partir de versões antigas. A `main` no commit `f69cf253fcc36baabb2980fcd7155393d73d778f` é a referência atual consolidada para iniciar a evolução de persistência, enquanto as PRs #10 e #12 permanecem pendentes e não devem ser incorporadas automaticamente nesta etapa.

A migração PostgreSQL será feita de forma incremental, reversível e com validação de dados antes de substituir a persistência atual.
