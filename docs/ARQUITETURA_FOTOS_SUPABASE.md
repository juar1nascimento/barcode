# Modelo definitivo proposto para fotos do patrimônio

## Decisão arquitetural

A imagem não será armazenada como BYTEA nem como Base64 dentro de JSONB.

O arquivo será armazenado no Supabase Storage e o PostgreSQL manterá apenas os metadados e a referência ao objeto.

Fluxo:

câmera -> compressão JPEG -> Supabase Storage -> patrimonio_fotos -> patrimônio

## Bucket

Nome proposto: `patrimonio-fotos`

Estrutura de objeto proposta:

`patrimonios/{patrimonio_id}/{ordem}-{sha256}.jpg`

## PostgreSQL

A tabela `public.patrimonio_fotos` mantém:

- `patrimonio_id`
- `ordem`
- `storage_bucket`
- `storage_path`
- `arquivo_nome`
- `mime_type`
- `tamanho_bytes`
- `largura`
- `altura`
- `sha256`
- `criado_em`

## Segurança

A migration cria RLS na tabela, mas não cria policies automaticamente. As policies dependem do mecanismo de autenticação/role usado pelo sistema e serão definidas depois da auditoria do login.

O bucket também não é criado pela migration. Isso evita colocar uma alteração de Storage em produção antes da definição das regras de acesso.

## Compatibilidade

A coluna legada `patrimonios.fotos`, se existir em algum ambiente, não é removida nesta etapa. A remoção somente ocorrerá depois de comprovar que não há dados legados necessários e que o novo fluxo de captura/recuperação funciona.

## Critério de produção

Não executar a migration antes de:

1. backup;
2. revisão das policies;
3. implementação do upload no Storage;
4. teste captura -> Storage -> PostgreSQL;
5. teste recuperação da foto;
6. teste no Almoxarifado Central SESA;
7. validação do CI.
