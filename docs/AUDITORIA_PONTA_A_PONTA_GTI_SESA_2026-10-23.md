# SIGS GTI SESA — Auditoria ponta a ponta e plano corretivo
**Data:** 2026-10-23  
**Repositório:** `juar1nascimento/barcode`  
**Branch de registro:** `fix/sigs-sheets-safe-reconciliation`  
**Status geral:** **BLOQUEADO PARA PRODUÇÃO** — auditoria estática/documental e inspeção de CI realizadas; simulação integrada real ainda incompleta.

## 1. Objetivo e limite desta rodada
Consolidar os bloqueios conhecidos e ordenar a manutenção corretiva por risco e dependência. A análise desta rodada usou o histórico do projeto, os documentos versionados, o PR #73, o PR #66 e os resultados do GitHub Actions disponíveis em 2026-10-23.

Nenhuma migration foi aplicada, nenhum worker foi executado contra produção, nenhuma planilha/linha foi alterada, nenhum bucket foi tornado público e nenhuma implantação foi realizada. Sem acesso autorizado e isolado aos serviços executáveis e seus dados de teste, não é correto declarar que todas as funções foram simuladas de ponta a ponta. Os itens abaixo distinguem evidência observada de validação ainda necessária.

## 2. Evidências observadas
- PR #73, **Fix safe reconciliation for SIGS Google Sheets sync**, está aberto como draft, não mesclado, base `main`, head `b2ff465c7ca80c531be0b7bf666a055fa3794a81`.
- No CI associado ao head do PR #73, **Testes Python** e **Inventário GTI SESA - Security** terminaram com sucesso; **System Audit** e **Inventário GTI SESA - CI** falharam.
- Nos dois jobs que falharam, compilação/testes estavam depois do passo de auditoria de dependências e foram ignorados. O motivo concreto do bloqueio foi `pip-audit`: Pillow `12.3.0` reportado com **24 vulnerabilidades conhecidas**, com correção indicada pelo scanner em `13.0.0`. A atualização não deve ser feita cegamente: verificar a restrição de versão de Streamlit e executar compatibilidade/testes antes de selecionar a versão corrigida.
- PR #66, relativo à segurança de pastas/lease do worker Drive e à validação isolada da migration, está aberto e não mesclado. Os runs consultados para seu head mostraram sucesso nos testes Python, Security, System Audit, CI, validação isolada da migration e contrato de wake-up. Isso não autoriza aplicar a migration em produção.
- O plano `PLANO_DASHBOARD_LOOKER_STUDIO.md` documenta a arquitetura analítica proposta: PostgreSQL como fonte de verdade, outbox para sincronização, Sheets como espelho e Looker Studio somente leitura. O documento é proposta técnica, não evidência de dashboard homologada.
- A documentação de BI registra risco bloqueante: uma migration versionada contém instrução para tornar público o bucket `patrimonio-fotos`; URLs assinadas com validade de 24 horas não são links permanentes adequados para miniaturas em cache. Isso não comprova que o bucket de produção esteja público; o estado real precisa de leitura autorizada.
- O histórico anterior registrou 28 patrimônios ativos e 23 fotos em uma observação de produção, sem substituir uma comparação atual, independente e linha a linha entre PostgreSQL e todas as abas do Sheets.
- A auditoria read-only disponível compara registros, cabeçalhos, IDs, duplicidades e campos críticos; sua execução com credenciais reais e evidência atual ainda precisa ser registrada no gate de homologação.

## 3. Bloqueios classificados

### P0 — impede a liberação
1. **CI vermelho no PR #73 por dependência vulnerável.** Resolver o conflito de dependências, selecionar versões compatíveis, executar novamente auditoria de dependências, compilação, testes, smoke test e segurança.
2. **PRs não integrados.** PR #73 continua draft e PR #66 não está mesclado. Revisar diffs, resultados de CI atuais e aprovação técnica antes de integrar.
3. **Segurança de fotos não homologada.** Não aplicar migration que torne o bucket público; confirmar o estado real do bucket com consulta somente leitura e definir uma estratégia de visualização que preserve as permissões.
4. **Falta de evidência integrada atual.** Não há nesta rodada prova executada de cadastro → PostgreSQL → outbox → worker → Sheets → leitura analítica, nem de reprocessamento, falhas e recuperação em ambiente isolado.
5. **Reconciliação Sheets x PostgreSQL ainda precisa de execução independente atual.** Confirmar zero IDs ausentes/duplicados, zero divergências críticas e correspondência de linhas sem pareamento ambíguo.
6. **Dashboard/galeria ainda não homologadas.** O plano existe, mas falta comprovar a conexão de todas as unidades, tipagem, agregações sem duplicação por junção 1:N, atualização, filtros e acesso autorizado às imagens.

### P1 — integridade e confiabilidade
7. **Identidade estável do patrimônio e da foto.** Confirmar que atualizações usam IDs estáveis, que número de patrimônio só é fallback inequívoco e que eventos repetidos não criam duplicatas.
8. **Concorrência e lease do worker Drive.** Validar perda/renovação de lease, expiração, dois workers concorrentes, retries, evento fora de ordem e retomada após falha usando apenas ambiente isolado.
9. **Pastas do Drive.** Confirmar que o destino é determinístico e que o fallback não cria pastas duplicadas nem move arquivos para a unidade errada.
10. **Cabeçalhos e esquema do Sheets.** Preflight estritamente read-only no fluxo normal; bloquear cabeçalho ausente/duplicado, aba desconhecida e conflitos sem normalização automática.
11. **Fotos.** Confirmar IDs, vínculo com patrimônio, hash/metadata, existência do arquivo, autorização e URL de abertura. Não depender de URL assinada expirada como chave ou endereço persistente.
12. **Observabilidade da outbox.** Verificar estados pendente, processando, sincronizado, retry e dead-letter, confirmação pós-escrita, idempotência e alertas de atraso.

### P2 — qualidade e entrega
13. **Aplicação e fluxos de negócio.** Testar login, autorização, consulta/pesquisa, cadastro, edição, exclusão, leitura de código de barras, movimentações/histórico e validações de formulário com fixtures de teste; confirmar regras e permissões por perfil.
14. **Deploy e operação.** Verificar configuração de ambiente, segredos fora do repositório/logs, health check, logs sem dados sensíveis, procedimento de rollback e smoke test pós-deploy.
15. **Documentação.** Atualizar os registros de decisão, critérios de aceite e evidências por gate; marcar explicitamente o que é proposto, executado, aprovado ou bloqueado.

## 4. Plano estratégico de manutenção corretiva

### Gate 0 — congelamento seguro
- Manter produção, banco, planilha, Drive e bucket sem alterações.
- Fixar commit/PR alvo e capturar os resultados completos dos workflows.
- Não executar workers ou migrations em ambientes produtivos durante a investigação.

**Aceite:** referência de código imutável e inventário de evidências anexado.

### Gate 1 — destravar CI e segurança (P0)
- Auditar `requirements.txt`, restrições de Streamlit e dependências transitivas que instalam Pillow.
- Selecionar uma combinação de versões compatível e corrigida; não usar atualização forçada sem matriz de compatibilidade.
- Rodar pip-audit, segurança estática, detecção de segredos, compilação, testes unitários e smoke test.
- Reexecutar os workflows completos nos PRs relevantes.

**Aceite:** CI e auditoria de dependências verdes; nenhuma falha ignorada por etapa anterior.

### Gate 2 — contrato de dados e sincronização (P0/P1)
- Executar auditoria read-only PostgreSQL x todas as abas de inventário.
- Comparar por ID estável; usar número apenas quando único dos dois lados.
- Relatar registros ausentes/extras, duplicidades, cabeçalhos, diferenças de campos e cobertura de IDs/fotos.
- Testar em fixtures/cópia a repetição de evento, timeout, falha após escrita, retry, eventos fora de ordem e conflitos.
- Confirmar que evento só fica sincronizado após leitura de confirmação.

**Aceite:** zero divergências críticas sem explicação aprovada; repetição idempotente; nenhuma escrita estrutural implícita.

### Gate 3 — worker Drive e migration isolada (P0/P1)
- Confirmar a aprovação dos testes de lease e segurança de pastas no PR #66.
- Executar somente em banco descartável/local isolado: aplicar migration, verificar invariantes e testar rollback/recriação quando aplicável.
- Validar destino de pasta, concorrência e reprocessamento sem acessar arquivos reais.
- Inspecionar a migration quanto a permissões de bucket e operações destrutivas.

**Aceite:** ensaio reproduzível com evidência, sem credenciais nem serviços de produção.

### Gate 4 — segurança das fotos (P0)
- Consultar o estado real do bucket e políticas de acesso em modo somente leitura.
- Confirmar se o conteúdo é restrito e quem deve visualizá-lo.
- Preferir armazenamento privado e galeria autenticada no SIGS quando o Looker não puder exibir miniaturas privadas com segurança.
- Não publicar o bucket nem persistir URL assinada expirável para resolver apresentação.

**Aceite:** teste de acesso autorizado e negado documentado; nenhuma ampliação de acesso sem aprovação institucional explícita.

### Gate 5 — homologação funcional ponta a ponta
Em ambiente isolado e com dados sintéticos, executar:
1. autenticação e autorização;
2. cadastro/edição/consulta de patrimônio;
3. geração e leitura do código de barras;
4. inclusão e consulta de fotos;
5. movimentação/histórico;
6. persistência no PostgreSQL;
7. publicação e recuperação da outbox;
8. atualização do Sheets por ID estável;
9. reconciliação de dados;
10. atualização das tabelas analíticas;
11. dashboard com filtros, indicadores e galeria/link de foto;
12. falhas de rede, retries, duplicidade e recuperação.

**Aceite:** evidência por fluxo, resultado esperado/obtido, logs sanitizados e nenhum bloqueio P0/P1 aberto.

### Gate 6 — decisão de release
- Revisão de código e segurança.
- Confirmar CI verde na revisão exata que será liberada.
- Plano de backup, janela, rollback e responsável pela autorização.
- Aplicação de migrations e deploy somente depois de aprovação explícita.
- Smoke test pós-deploy e reconciliação somente leitura.

**Aceite final:** todos os gates obrigatórios aprovados e autorização de produção registrada.

## 5. Matriz de simulação funcional

| Fluxo | Situação nesta rodada | Evidência exigida para aprovação |
|---|---|---|
| Login/autorização | Não simulado ao vivo | Testes por perfil e negação de acesso |
| CRUD de patrimônio | Não simulado ao vivo | Casos de criar, ler, atualizar, excluir e validar |
| Código de barras | Não simulado ao vivo | Leitura, correspondência exata e erro de código inválido |
| Fotos/Drive | Parcialmente documentado; não homologado | Upload/consulta em ambiente isolado, ID/hash e permissão |
| Outbox/worker | Testes automatizados associados ao PR #66 passaram em runs consultados; fluxo completo ainda não comprovado | Retry, concorrência, lease, idempotência e confirmação pós-escrita |
| PostgreSQL ↔ Sheets | Correção proposta no PR #73; CI bloqueado por dependências | Auditoria linha a linha e teste de reconciliação |
| Migração SQL | Validação isolada do PR #66 reportada como sucesso; não aplicada em produção | Repetição em ambiente descartável e revisão de segurança |
| Looker Studio | Plano técnico existente; dashboard não homologada nesta rodada | Fonte consolidada, filtros, agregações, atualização e permissões |
| Recuperação/rollback | Não comprovado nesta rodada | Ensaio documentado em ambiente isolado |
| CI/segurança | Bloqueado no PR #73 | Todos os jobs obrigatórios verdes na revisão candidata |

## 6. Critérios objetivos de liberação
A produção permanece bloqueada até que:
- [ ] os workflows obrigatórios estejam verdes no commit candidato;
- [ ] a auditoria de dependências não reporte vulnerabilidades bloqueantes sem mitigação aprovada;
- [ ] o diff de cada PR tenha revisão aprovada;
- [ ] a reconciliação PostgreSQL x Sheets esteja concluída e anexada;
- [ ] os testes de idempotência, concorrência, retry e recuperação estejam aprovados;
- [ ] o estado e as políticas do bucket estejam verificados sem ampliar acesso indevidamente;
- [ ] os fluxos funcionais tenham evidências em ambiente isolado;
- [ ] a camada analítica esteja validada, ou formalmente separada do release operacional se não for requisito bloqueante;
- [ ] exista plano de rollback e autorização explícita para a mudança produtiva.

## 7. Próxima ação prioritária
**Resolver primeiro o bloqueio do CI do PR #73 causado pelo Pillow 12.3.0**, sem contornar ou desabilitar o scanner. Em seguida, executar novamente o pipeline completo; somente então avançar para a reconciliação read-only atual e homologação integrada.

## 8. Referências de trabalho
- PR #73: https://github.com/juar1nascimento/barcode/pull/73
- PR #66: https://github.com/juar1nascimento/barcode/pull/66
- Contrato analítico: `PLANO_DASHBOARD_LOOKER_STUDIO.md`
- Auditoria técnica existente: `AUDITORIA_TECNICA.md`
- Auditoria independente de Sheets/PostgreSQL: `auditoria_sigs_sheets_somente_leitura.py` e `auditoria_analitica_readonly.py`

**Conclusão:** esta auditoria identificou bloqueios concretos e organizou a sequência corretiva, mas não certifica a prontidão para produção. O sistema só deve ser declarado pronto após a execução e aprovação dos gates com evidências atuais.


## 9. Execução do Gate 1 — 2026-10-24

### Ação aplicada
- O log do CI do PR #73 reportou Pillow `12.3.0` com 24 vulnerabilidades conhecidas e indicou `13.0.0` como versão corrigida.
- Atualizado somente o pin `pillow==12.3.0` para `pillow==13.0.0` em `requirements.txt`, na branch `fix/sigs-sheets-safe-reconciliation`.
- Commit da correção: `0c829410fff4d737336934142eb80c3f19dc1f9b`.
- Nenhum scanner foi desabilitado e nenhum serviço produtivo foi alterado.

### Estado de validação
- O commit foi confirmado no GitHub.
- No instante da consulta, ainda não havia runs de workflow retornados para esse SHA. Portanto, a compatibilidade com Streamlit/OpenCV e o resultado do `pip-audit` permanecem **pendentes de CI**.
- Não declarar Gate 1 aprovado até obter os jobs completos e verificar que auditoria de dependências, compilação, testes, segurança estática, verificação de segredos e smoke test terminaram sem falhas ou etapas essenciais ignoradas.
- Se o CI apontar incompatibilidade, corrigir a restrição específica com evidência do log; não reduzir o nível de segurança nem ignorar o scanner.

### Próxima verificação
Consultar os workflows do PR #73 e os logs completos do novo commit. Se aprovados, seguir para o Gate 2: auditoria PostgreSQL × todas as abas do Google Sheets em modo somente leitura.

### Ajuste de compatibilidade após o primeiro CI
- A primeira tentativa de usar Pillow 13.0.0 foi corretamente rejeitada pelo resolvedor: Streamlit 1.63.0 exige `pillow<13`. Não se desativou nem contornou essa validação.
- A documentação oficial de Streamlit/PyPI indica que Streamlit 1.66.1 permite Pillow `>=9.2.0,<14`; portanto, a branch foi ajustada para `streamlit==1.66.1` e manteve `pillow==13.0.0`.
- Commit de alinhamento: `4e0a4262f80454ad6967e2bd89365a4cc6be71d2`.
- **Compatibilidade ainda não aprovada:** aguardar o CI dessa combinação, incluindo testes funcionais do app e integração com `streamlit-webrtc`. Não promover dependências a produção sem esses resultados.
