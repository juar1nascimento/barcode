# Plano de Baseline Não Destrutivo — GTI-SESA

## Objetivo

Sincronizar o histórico de migrations do repositório com o schema já existente no projeto Supabase sem recriar tabelas, sem alterar dados e sem reaplicar a migration legada.

## Estado confirmado antes do baseline

- O banco publicado já possui as tabelas unidades, setores, patrimonios e patrimonio_fotos.
- As estruturas, FKs, checks, índices e regras de unicidade auditadas estão coerentes com o código.
- A constraint de unidades.tipo já aceita UBS, URS e ALMOX.
- O histórico de migrations consultado no projeto está vazio.
- Existe migrations/001_almoxarifado_tipo.sql, mas ela é uma alteração incremental legada e não é o baseline do banco atual.

## Regra de segurança

Nesta fase não executar no banco:

- CREATE TABLE, ALTER TABLE ou DROP TABLE;
- criação/remoção de índices;
- alteração ou recriação de constraints;
- alterações de RLS/policies;
- INSERT/UPDATE/DELETE/TRUNCATE de dados;
- aplicação da 001_almoxarifado_tipo.sql.

## Estratégia para a próxima execução

A documentação atual do Supabase orienta que, quando o banco remoto já contém mudanças que não estão nas migrations locais, o primeiro passo é usar supabase db pull para capturar o schema remoto em uma migration de baseline. A documentação também informa que esse pull pode registrar o baseline como já aplicado no histórico remoto, evitando que o SQL seja executado novamente. citeturn0search0turn0search1

A execução operacional deverá seguir esta ordem:

1. Verificar a versão da Supabase CLI com supabase --version.
2. Verificar os comandos/flags disponíveis com supabase --help e supabase db pull --help.
3. Inicializar/validar a estrutura local supabase/ somente se necessário.
4. Vincular o projeto correto (vgabxdprocwmpmhoxrgt) somente no ambiente local.
5. Executar supabase db pull para gerar o baseline a partir do estado remoto.
6. Revisar integralmente o SQL gerado antes de qualquer push.
7. Confirmar que o baseline representa o estado já existente e não contém alterações indesejadas.
8. Se o CLI solicitar atualização do histórico remoto para marcar o baseline como aplicado, essa etapa será tratada separadamente e somente após revisão explícita do resultado. A operação de migration repair, quando necessária, altera apenas o registro de histórico e não executa/reverte o SQL, conforme a documentação atual. citeturn0search0
9. Só depois validar supabase migration list e a consistência local/remota.
10. A partir daí, migrations futuras serão incrementais e representarão somente mudanças novas.

## Ponto importante sobre postgresql_schema.sql

O arquivo continua sendo a documentação humana/canônica do schema observado. Ele não deve ser usado como migration de baseline executável neste momento, porque contém definições de tabelas e índices que não são necessárias para registrar o histórico do banco existente.

O baseline operacional deve ser gerado pelo mecanismo oficial do Supabase CLI a partir do banco remoto, em vez de ser inventado manualmente. A documentação atual indica que o db pull inicial cria uma migration representando o schema remoto e que esse arquivo passa a ser a base das alterações futuras. citeturn0search1

## Sobre migrations/001_almoxarifado_tipo.sql

Não renomear, reaplicar ou promover automaticamente esse arquivo a baseline.

Depois que o baseline oficial for gerado e revisado, a migration 001 deverá ser tratada como histórico legado separado. Se ela não representar uma mudança que ainda precise ser executada sobre o estado atual, sua disposição será decidida em uma etapa própria, sem modificar o banco.

## Critério de conclusão do baseline

A etapa somente será considerada concluída quando houver evidência de que:

- o baseline local descreve o estado remoto auditado;
- o banco não recebeu DDL ou alteração de dados durante a captura;
- o histórico remoto e os arquivos locais estiverem coerentes;
- não houver tentativa de reaplicar objetos já existentes;
- a migration 001 não tiver sido executada como baseline;
- o próximo passo puder ser uma migration incremental controlada.

## Observação sobre o Data API

A Supabase anunciou mudança de exposição automática de novas tabelas no Data API, com aplicação a projetos existentes em 30 de outubro de 2026. Isso não altera o baseline atual, mas deverá ser considerado na futura revisão de grants/exposição das tabelas do GTI-SESA. citeturn0search4

## Fontes oficiais consultadas

- Supabase — Database Migrations.
- Supabase — Local development workflow / db pull.
- Supabase — Diff engines.
- Supabase — Changelog sobre exposição do Data API.

Nenhuma dessas referências autoriza, por si só, a execução de db push neste estágio. O baseline deve ser capturado e revisado antes de qualquer aplicação de migration.
