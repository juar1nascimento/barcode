# Auditoria de Consistência — Etapa 9

## Escopo

Auditoria somente de leitura da branch `feat/supabase-source-of-truth` contra o schema atualmente publicado no projeto Supabase.

Nenhuma operação `CREATE`, `ALTER`, `DROP`, migração de dados ou alteração de RLS foi executada nesta etapa.

## Resultado

### 1. Schema canônico

O arquivo `postgresql_schema.sql` agora documenta as quatro tabelas observadas no banco:

- `unidades`
- `setores`
- `patrimonios`
- `patrimonio_fotos`

Também documenta os índices, chaves estrangeiras, regras de unicidade e checks relevantes.

### 2. Código da aplicação

A auditoria encontrou referências coerentes com o schema em:

- `postgresql_persistencia.py`
- `fotos_patrimonio.py`
- `supabase_storage.py`
- `migrar_google_para_postgresql.py`

As referências a `patrimonio_fotos` usam as colunas existentes no banco, incluindo `ordem`, `storage_bucket`, `storage_path`, `arquivo_nome`, `mime_type`, `tamanho_bytes`, `largura`, `altura`, `sha256` e `criado_em`.

A lista de tipos de patrimônio do código também coincide com o CHECK observado no banco.

### 3. Migração legada encontrada

Existe `migrations/001_almoxarifado_tipo.sql`.

Ela **não deve ser tratada como primeira migration/base histórica do banco existente**. Seu objetivo é alterar a constraint de `unidades.tipo`, inclusive executando `ALTER TABLE ... DROP CONSTRAINT` e `ADD CONSTRAINT`.

No banco atualmente auditado, a constraint já está correta:

`unidades_tipo_check` → `tipo IN ('UBS', 'URS', 'ALMOX')`.

Portanto, executar essa migration agora seria uma alteração desnecessária no banco já funcional.

### 4. Histórico de migrations do Supabase

O histórico consultado no projeto continua sem migrations registradas.

Isso significa que o estado publicado do banco e o histórico versionado do repositório ainda representam duas linhas históricas diferentes:

- **estado real:** schema já existente e funcional;
- **histórico:** sem baseline registrado no Supabase.

Não é seguro resolver essa diferença recriando as tabelas nem reaplicando a migration 001.

## Conclusão da Etapa 9

A auditoria código ↔ schema está consistente para as entidades principais.

O bloqueio restante para uma primeira migration segura é **histórico/versionamento**, não uma divergência estrutural conhecida.

### Próximo passo seguro

Preparar uma estratégia de **baseline não destrutivo**, sem executar no Supabase:

1. preservar o banco publicado como está;
2. separar o estado atual (baseline) das migrations incrementais futuras;
3. não reaplicar `001_almoxarifado_tipo.sql`;
4. definir o procedimento de versionamento que registre o estado existente sem recriar objetos;
5. somente depois realizar uma validação controlada contra o ambiente publicado.

## Regra de segurança

Até a aprovação explícita da fase de aplicação, não executar:

- `CREATE TABLE`;
- `ALTER TABLE`;
- `DROP TABLE`;
- `CREATE/DROP INDEX`;
- alterações de constraints;
- alterações de RLS/policies;
- migração ou alteração de dados.

