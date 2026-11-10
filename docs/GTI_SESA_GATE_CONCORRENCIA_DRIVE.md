# GTI SESA — Gate de concorrência para pastas de patrimônio no Drive

**Estado:** proposta técnica; não implementada  
**Data:** 2026-10-13  
**Relacionados:** [Issue #67](https://github.com/juar1nascimento/barcode/issues/67), [PR #66](https://github.com/juar1nascimento/barcode/pull/66)

## Objetivo e bloqueio

Impedir que duas execuções do `outbox-drive-worker` criem pastas `Patrimônio {numero_patrimonio}` duplicadas dentro da pasta exata da unidade. A criação no Drive não oferece unicidade atômica por nome; uma segunda consulta isolada não resolve a corrida.

**A PR #66 deve continuar sem merge/implantação até este gate ser implementado e aprovado independentemente.** Não ativar wake-up, não processar outbox de produção e não executar chamadas reais ao Drive nesta etapa.

## Opção preferida para implementação

Adotar coordenação durável no PostgreSQL, com chave determinística do destino (ID da pasta exata da unidade + ID do patrimônio), em vez de mutex em memória, pois as Edge Functions podem executar em instâncias distintas.

A coordenação deve ser uma concessão/lease atômica, com:
- chave única para o patrimônio dentro da unidade;
- token aleatório do proprietário e prazo de expiração;
- aquisição atômica que recuse um segundo proprietário enquanto a concessão válida existir;
- renovação condicionada ao mesmo token, caso a duração máxima da operação exija;
- liberação condicionada ao token, para que um worker antigo não libere a concessão de outro;
- recuperação após falha por expiração e logs sem tokens, credenciais ou conteúdo sensível;
- privilégio mínimo: escrita da concessão apenas para o worker/rotina autorizada.

Não manter lock de sessão PostgreSQL presumindo que chamadas HTTP ao Drive ocorram dentro da mesma sessão/transação. A arquitetura de Edge Function com chamadas HTTP exige coordenação durável explícita.

## Sequência obrigatória dentro da concessão

1. Resolver patrimônio, unidade e pasta exata da unidade; falhar fechado se qualquer vínculo ou pasta da unidade for ausente/ambíguo.
2. Adquirir a concessão para a chave estável do patrimônio. Se ocupada, não criar pasta; deixar o evento apto a retry com erro operacional identificável.
3. Consultar a pasta filha exata `Patrimônio {numero_patrimonio}`.
4. Se existir exatamente uma, reutilizar o ID encontrado.
5. Se não existir, verificar que a concessão ainda pertence ao worker e criar uma única pasta filha.
6. Depois da criação, consultar novamente e validar exatamente uma pasta, usando o ID retornado como informação auxiliar, nunca como substituto da validação.
7. Se a consulta retornar mais de uma, falhar fechado, registrar conflito e não enviar a foto a destino ambíguo.
8. Somente depois de resolver e validar a pasta, continuar a idempotência do arquivo/foto pela chave da outbox e marcar o evento como sincronizado após a confirmação correspondente.
9. Liberar a concessão em `finally`, condicionada ao token do proprietário. Se a execução cair, a expiração deve permitir recuperação controlada.

## Limite importante de garantia

A lease reduz e coordena a concorrência entre workers cooperantes, mas não torna a operação de criação do Google Drive transacional. Se uma requisição de criação permanecer em voo após a expiração da lease, uma segunda execução pode começar e ambas as requisições podem terminar. Portanto, a implementação deve escolher um prazo conservador compatível com o limite de execução, renovar/validar a concessão, reconsultar depois de qualquer criação e falhar fechado diante de duplicidade. Não declarar garantia matemática de unicidade enquanto o Drive não fornecer uma primitiva de criação condicional idempotente adequada.

## Integração com a outbox

- A lease por patrimônio complementa — não substitui — o claim por evento da outbox.
- `FOR UPDATE SKIP LOCKED` impede dois consumidores de reivindicar o mesmo evento; não serializa eventos diferentes do mesmo patrimônio.
- Falha ao adquirir lease não deve marcar o evento como sincronizado nem descartar a foto; deve seguir a política de retry existente e registrar motivo seguro.
- O estado `synced` só pode ser confirmado depois de pasta única validada e arquivo verificado segundo o contrato atual.
- Não criar fallback para raiz do Drive, não inventar IDs e não enviar arquivos quando o destino estiver ambíguo.

## Gates de aceitação antes de considerar merge

1. Revisar o esquema e os privilégios da tabela/RPC de lease e confirmar compatibilidade com o modelo atual de outbox.
2. Testes isolados sem chamadas reais ao Drive: pasta única existente; pasta ausente; lookup ambíguo; erro HTTP de criação; resposta sem ID; concessão ocupada; expiração/recuperação; liberação por token incorreto; duas execuções concorrentes; falha após criação e antes de confirmar outbox.
3. Demonstrar que, em concorrência controlada, apenas o proprietário da concessão entra na seção de criação, e que qualquer duplicidade observada bloqueia upload.
4. CI e revisão independente do diff completo.
5. Confirmar separadamente flags, secrets e configuração do ambiente antes de qualquer implantação; wake-up permanece desativado até aprovação específica.

## Estado desta etapa

Este arquivo é documentação de desenho, não uma mudança de runtime. Nenhum teste, auditoria, migration, chamada ao Drive, alteração de secrets/flags, processamento de outbox ou implantação foi realizado.
