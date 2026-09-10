# AUDITORIA POSTGRESQL — ETAPA 9

## 1. Objetivo

Avaliar o repositório `juar1nascimento/barcode` e definir a forma mais segura de substituir a persistência operacional baseada em Google Sheets/Excel por PostgreSQL, preservando as regras atuais do inventário e preparando o sistema para uso concorrente.

Auditoria realizada sobre o estado atual da branch `main` (commit de referência: `f69cf253fcc36baabb2980fcd7155393d73d778f`) e sobre a cópia do projeto fornecida para esta etapa.

## 2. Diagnóstico atual

### 2.1 Persistência do inventário

O backend principal está em `Tabela_de_dados_Inventario_7_2.py`.

Atualmente existem dois destinos de persistência:

1. **Google Sheets** — é o destino online efetivamente considerado como salvo.
2. **XLSX local** — é mantido como backup local em arquivos `Inventario_<unidade>.xlsx`.

O fluxo de cadastro é aproximadamente:

`Streamlit -> sistema_inventario.py -> registrar_patrimonio() -> carregar_dados_excel() -> _anexar_no_google() -> Google Sheets`

A função `registrar_patrimonio()` já possui validações importantes: unidade, setor, tipo, número de patrimônio e prevenção de duplicidade.

### 2.2 Schema lógico já consolidado

O projeto já possui um schema canônico de cinco campos:

- `Setor`
- `Tipo de Patrimônio`
- `Nº de Patrimônio`
- `Fabricante`
- `Data Cadastro`

Essa estrutura deve ser preservada na migração.

### 2.3 Regras que não devem ser alteradas nesta etapa

A migração de banco não deve mudar as regras funcionais já estabilizadas:

- Tipos oficiais: `CPU`, `Monitores`, `Teclado`, `Mouse`, `Imprenssoras`, `Outros Dispositivos`.
- `Local / Setor` não deve voltar a ser opção de menu.
- Menus de setores devem continuar controlados e ordenados.
- Não devem reaparecer opções legadas como `Monitor`, `Computador`, `Fabricante Monitor`, `Fabricante Computador` etc.
- A gravação deve continuar impedindo patrimônio duplicado.

### 2.4 Entrada e saída

`entrada_equipamentos.py` e `saida_equipamentos.py` atualmente exibem confirmação na interface, mas não possuem uma camada de persistência equivalente ao inventário. Portanto, a migração para PostgreSQL é uma oportunidade para transformar entrada, saída e transferência em operações transacionais reais, em vez de apenas mensagens de sucesso na tela.

### 2.5 Autenticação

`login.py` ainda usa `db_usuarios.json` para armazenar usuários. Esse arquivo não deve ser simplesmente misturado à tabela de inventário. Recomenda-se uma etapa posterior para migrar usuários para PostgreSQL, mantendo a autenticação como domínio separado.

### 2.6 Dependências

`requirements.txt` já contém `duckdb`, além de bibliotecas Google Sheets, mas DuckDB não é o mecanismo atual de persistência do inventário. Para PostgreSQL, a dependência recomendada é SQLAlchemy + `psycopg` (psycopg 3).

## 3. Riscos encontrados

### Alto

**Google Sheets como banco operacional.** O código precisa ler/reler planilhas, detectar duplicidades e confirmar gravações. Isso aumenta a complexidade e o risco de corrida entre sessões.

**XLSX como backup operacional.** Arquivos locais não são um armazenamento confiável para uma aplicação web hospedada.

**Ausência de transação de banco.** Cadastro, entrada, saída e futuras transferências não têm uma unidade transacional comum.

### Médio

**Modelo legado de colunas.** O backend já normaliza formatos históricos. A migração deve importar para o schema relacional canônico, e não reproduzir o modelo antigo de colunas por tipo.

**Exclusão.** A interface ainda carrega compatibilidade com a lógica antiga; no PostgreSQL deve ser implementada por chave/ID do registro, com regras explícitas de integridade.

### Baixo/Médio

**Credenciais.** A nova conexão PostgreSQL não deve ser colocada no código nem versionada no GitHub.

## 4. Arquitetura recomendada

### Camadas

```text
Streamlit UI
    |
    v
Serviços/domínio
    |
    v
Repositórios PostgreSQL
    |
    v
SQLAlchemy + psycopg 3
    |
    v
PostgreSQL
```

A interface (`sistema_inventario.py`) não deve executar SQL diretamente. O acesso ao banco deve ficar concentrado em um módulo de persistência/repositório.

### Módulos sugeridos

```text
db/
  connection.py
  models.py
  repositories.py
  migrations/
services/
  inventario_service.py
  movimentacao_service.py
```

Na primeira fase, não é necessário reescrever toda a interface. O objetivo é substituir o adaptador de persistência mantendo as funções públicas já utilizadas pela UI, especialmente `carregar_dados_excel`, `registrar_patrimonio`, `registrar_patrimonios_em_lote`, `excluir_setor` e `excluir_patrimonio` por equivalentes orientados ao PostgreSQL.

## 5. Modelo PostgreSQL proposto

O modelo inicial deve ser relacional, evitando criar uma coluna diferente para cada tipo de patrimônio.

### `unidades`

- `id` BIGSERIAL PRIMARY KEY
- `nome` VARCHAR(150) UNIQUE NOT NULL
- `tipo` VARCHAR(10) NOT NULL — `URS` ou `UBS`
- `ativo` BOOLEAN NOT NULL DEFAULT TRUE

### `setores`

- `id` BIGSERIAL PRIMARY KEY
- `nome` VARCHAR(150) UNIQUE NOT NULL
- `ativo` BOOLEAN NOT NULL DEFAULT TRUE

### `tipos_patrimonio`

- `id` BIGSERIAL PRIMARY KEY
- `nome` VARCHAR(80) UNIQUE NOT NULL
- `ativo` BOOLEAN NOT NULL DEFAULT TRUE

### `fabricantes`

- `id` BIGSERIAL PRIMARY KEY
- `nome` VARCHAR(120) UNIQUE NOT NULL
- `ativo` BOOLEAN NOT NULL DEFAULT TRUE

### `patrimonios`

- `id` BIGSERIAL PRIMARY KEY
- `numero_patrimonio` VARCHAR(100) NOT NULL UNIQUE
- `unidade_id` BIGINT NOT NULL REFERENCES unidades(id)
- `setor_id` BIGINT NOT NULL REFERENCES setores(id)
- `tipo_id` BIGINT NOT NULL REFERENCES tipos_patrimonio(id)
- `fabricante_id` BIGINT REFERENCES fabricantes(id)
- `data_cadastro` TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
- `ativo` BOOLEAN NOT NULL DEFAULT TRUE

### `movimentacoes`

Para a próxima fase:

- `id` BIGSERIAL PRIMARY KEY
- `patrimonio_id` BIGINT NOT NULL REFERENCES patrimonios(id)
- `tipo` VARCHAR(20) NOT NULL — entrada, saída ou transferência
- `unidade_origem_id` BIGINT REFERENCES unidades(id)
- `unidade_destino_id` BIGINT REFERENCES unidades(id)
- `setor_origem_id` BIGINT REFERENCES setores(id)
- `setor_destino_id` BIGINT REFERENCES setores(id)
- `motivo` TEXT
- `observacao` TEXT
- `usuario_id` BIGINT NULL
- `criado_em` TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP

O histórico de movimentações deve ser append-only sempre que possível. O estado atual do patrimônio fica em `patrimonios`; o histórico fica em `movimentacoes`.

## 6. Integridade e concorrência

A regra crítica de unicidade deve ser garantida pelo PostgreSQL, e não apenas pelo Python:

```sql
CREATE UNIQUE INDEX uq_patrimonios_numero
ON patrimonios (numero_patrimonio);
```

O cadastro deve utilizar transação e tratar `UNIQUE VIOLATION` como patrimônio já cadastrado.

Isso elimina a dependência do padrão atual de “ler primeiro, verificar depois, anexar e reler”.

## 7. Configuração de conexão

A aplicação deve receber a conexão por Secret/variável de ambiente.

Exemplo local:

```toml
[connections.inventory_db]
type = "sql"
url = "postgresql+psycopg://inventario_app:SENHA@localhost:5432/gti_inventario"
```

O arquivo `.streamlit/secrets.toml` deve ficar no `.gitignore` e nunca ser enviado ao GitHub.

## 8. Estratégia de migração

Não substituir o Google Sheets de uma vez.

### Fase A — Banco local

1. Instalar PostgreSQL 18.
2. Criar banco `gti_inventario`.
3. Criar usuário de aplicação `inventario_app`.
4. Criar schema e tabelas.
5. Criar índices e constraints.
6. Testar conexão pelo terminal e pela aplicação.

### Fase B — Importação

1. Fazer uma cópia somente leitura dos dados históricos.
2. Normalizar as abas existentes para o schema canônico de cinco campos.
3. Remover duplicidades pelo número de patrimônio.
4. Validar unidades, setores, tipos e fabricantes.
5. Importar para PostgreSQL.
6. Executar relatório de contagem antes/depois.
7. Não apagar o Google Sheets durante essa fase.

### Fase C — Dupla validação

Durante um período curto, comparar leituras PostgreSQL x Google Sheets sem usar o Google Sheets como fonte primária de novos registros.

### Fase D — PostgreSQL como fonte oficial

Novo cadastro, exclusão, entrada, saída e transferência passam a ser transacionais no PostgreSQL.

### Fase E — Retirada do Google Sheets

Somente depois da validação dos dados e do funcionamento da aplicação em produção.

## 9. Ponto crítico: Streamlit Cloud

O PostgreSQL instalado neste computador será adequado para desenvolvimento local. Ele não deve ser tratado como banco de produção para uma aplicação hospedada no Streamlit Community Cloud, porque `localhost` no servidor do Streamlit é o próprio ambiente remoto, não este computador.

Para produção no Streamlit Cloud, o banco deverá ser acessível pela internet através de um PostgreSQL hospedado, com TLS/SSL e credenciais armazenadas nos Secrets do Streamlit.

Portanto, a arquitetura recomendada é:

```text
DESENVOLVIMENTO
PC -> PostgreSQL local

PRODUÇÃO
Streamlit Cloud -> PostgreSQL hospedado
```

O código permanece o mesmo; somente a URL/Secret da conexão muda por ambiente.

## 10. Ordem segura das próximas etapas

1. Instalar e testar PostgreSQL local.
2. Criar banco e usuário sem tocar ainda no código de produção.
3. Criar branch de migração.
4. Adicionar SQLAlchemy + psycopg.
5. Criar módulo de conexão e modelo.
6. Criar migrações.
7. Criar importador do Google Sheets/XLSX.
8. Importar e validar dados históricos.
9. Criar testes de persistência e concorrência.
10. Trocar o adaptador do inventário para PostgreSQL.
11. Implementar movimentações de entrada/saída/transferência.
12. Testar localmente.
13. Configurar PostgreSQL hospedado para produção.
14. Configurar Secrets do Streamlit.
15. Fazer deploy.
16. Somente após validação, desativar a escrita no Google Sheets.

## 11. Conclusão

A migração para PostgreSQL é tecnicamente recomendada e resolve o principal limite estrutural identificado: usar Google Sheets/XLSX como camada de persistência de uma aplicação multiusuário.

A melhor estratégia não é “sincronizar o GitHub com PostgreSQL”. O GitHub deve armazenar o **código e as migrações**; PostgreSQL deve armazenar os **dados operacionais**. A aplicação é a ponte entre os dois.

A migração deve preservar o schema canônico e as regras já estabilizadas, introduzindo uma camada de persistência PostgreSQL com transações, constraints e histórico de movimentações.

## 12. Referências técnicas

- PostgreSQL 18 — documentação oficial.
- Streamlit — `st.connection()` / SQLConnection.
- Streamlit — `st.secrets` e gerenciamento seguro de credenciais.
- SQLAlchemy — dialeto PostgreSQL com psycopg 3.
