# GTI SESA — Gate separado de implantação e validação controlada

**Estado:** PREPARAÇÃO — NÃO AUTORIZA IMPLANTAÇÃO  
**Data de preparação:** 2026-10-19  
**PR do worker:** [#66](https://github.com/juar1nascimento/barcode/pull/66)  
**Migration proposta:** `20261013130000_gti_drive_folder_lease.sql`  
**Regra central:** não ativar processamento geral da outbox nem o wake-up automático durante este gate.

## 1. Situação de entrada

- Os cinco workflows do commit `aff5d624a674a169bb4372e660018518fec60737` foram consultados e constam como `success`.
- A lista de reviews do PR #66 está vazia na última verificação. A revisão independente permanece bloqueadora.
- A migration de lease está apenas no PR; não foi aplicada por este gate.
- Não houve deploy, alteração de secrets/flags, gravação no Drive ou processamento de outbox como parte desta preparação.

## 2. Gate A — revisão independente antes do merge

Um revisor diferente do autor deve revisar o SHA exato do PR, incluindo:

- `supabase/functions/outbox-drive-worker/index.ts`
- `supabase/functions/outbox-drive-worker/drive_folder_safety.ts`
- `supabase/functions/outbox-drive-worker/drive_folder_safety_test.ts`
- `supabase/migrations/20261013130000_gti_drive_folder_lease.sql`

Checklist mínimo:
- [ ] Confirmar que o patrimônio da linha da foto corresponde a `patrimonio_id` do item de outbox; divergência deve falhar fechada.
- [ ] Confirmar que a busca por `gti_outbox_id` detecta zero, um ou múltiplos arquivos; múltiplos resultados devem falhar fechada, sem escolher `files[0]`.
- [ ] Avaliar a duração/expiração da lease e comportamento quando chamadas ao Drive demoram ou a liberação falha.
- [ ] Validar privilégios/RLS, `SECURITY DEFINER`, `search_path`, atomicidade da lease e compatibilidade da migration com o schema real.
- [ ] Confirmar os testes isolados e CI verde para o SHA final revisado.
- [ ] Registrar no PR uma review formal de aprovação ou pedidos de alteração.

**Saída do Gate A:** somente após aprovação independente e resolução dos bloqueios pode-se considerar merge. CI verde, por si só, não é aprovação de código nem prova de fluxo real.

## 3. Gate B — preparação de implantação (sem executar)

Antes de qualquer mudança:
- [ ] Registrar SHA aprovado, diff final, plano de implantação e rollback.
- [ ] Confirmar backup/recuperação e compatibilidade da migration com o schema de produção por procedimento autorizado.
- [ ] Confirmar que `DRIVE_PROCESSING_ENABLED` permanece `false` e `GTI_OUTBOX_WAKEUP_WORKER_ENABLED` permanece `false`.
- [ ] Confirmar que nenhum agendamento, webhook ou caller pode invocar `mode=process` inadvertidamente.
- [ ] Definir o patrimônio/foto de teste autorizado, esperado, isolado e reversível; não selecionar uma linha real por suposição.
- [ ] Garantir que a execução controlada possa reivindicar **somente** o evento explicitamente autorizado.

**Bloqueio importante:** o modo `process` atual reivindica itens pela função geral `claim_patrimonio_fotos_drive_outbox`. Usar `limit=1` não garante que o item seja a foto de teste. Portanto, não executar `mode=process` para testar uma única foto enquanto não houver um mecanismo estritamente direcionado ao evento autorizado, ou prova auditável de que a fila elegível contém exclusivamente o canário.

## 4. Gate C — validações somente leitura após autorização de implantação

Com as flags de processamento ainda desligadas, executar e guardar a resposta de cada verificação, sem divulgar tokens ou URLs assinadas:

1. Verificar configuração e destino Drive com `mode=validate_drive`; esperado: `external_write=false`, pasta de destino confirmada e permissão de escrita informada.
2. Executar `mode=dry_run` com limite pequeno; esperado: `external_write=false`, `claimed_changes=0`, `synced_changes=0`. Esse modo baixa objetos do Storage para verificar tamanho/hash, mas não deve gravar no Drive nem reivindicar eventos.
3. Confirmar que flags, fila e estados dos eventos não foram alterados.
4. Se qualquer resposta for inesperada, interromper e não prosseguir para teste com escrita.

Essas verificações não provam upload real nem sincronização visual no Sheets.

## 5. Gate D — canário de uma única foto (gate futuro e separado)

Este gate exige autorização explícita e uma forma segura de selecionar um único evento. Não usar a fila geral como seletor.

Pré-condições:
- [ ] Revisor independente aprovado e PR integrado conforme procedimento do projeto.
- [ ] Migration aplicada por etapa autorizada e resultado verificado.
- [ ] Worker implantado com processamento geral e wake-up ainda desativados.
- [ ] Evento canário inequívoco, com patrimônio/foto conferidos, autorização registrada e método de rollback definido.
- [ ] Executor direcionado por ID de evento validado no servidor, que não reivindique outros itens. Se isso não existir, **não executar o canário em produção**.

Execução e verificação — apenas após autorização específica:
- [ ] Processar exatamente o evento canário, sem liberar lote ou wake-up.
- [ ] Verificar que apenas a pasta exata do patrimônio foi usada e que não houve pasta/arquivo duplicado.
- [ ] Comparar ID da foto, patrimônio, nome, tamanho e SHA-256 entre Storage, arquivo no Drive e metadados finalizados.
- [ ] Confirmar que apenas o evento autorizado mudou de estado e que os demais itens da fila permaneceram inalterados.
- [ ] Verificar o link do Drive e o resultado de apresentação no destino esperado, sem tornar público o bucket privado.
- [ ] Registrar logs redigidos, IDs não secretos, resultados e decisão de aprovação/reversão.

Qualquer divergência, duplicata, mismatch de patrimônio, erro de hash ou alteração de evento não autorizado implica **PARAR**, preservar evidências e não repetir automaticamente.

## 6. Gate E — processamento geral

Fora do escopo desta etapa. Exige nova decisão explícita, evidência satisfatória do canário, revisão de limites/retentativas, observabilidade e plano de interrupção. Não habilitar `DRIVE_PROCESSING_ENABLED`, wake-up, agendamentos ou processamento em lote como consequência automática de um canário bem-sucedido.

## Resultado desta preparação

**Estado final: BLOQUEADO PARA IMPLANTAÇÃO até revisão independente.** Este documento prepara os critérios e a sequência; não aplica migration, não faz deploy, não altera flags/secrets e não executa a fila.
