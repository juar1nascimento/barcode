# Auditoria técnica — Sistema de Inventários GTI-SESA

## Escopo

Auditoria do pacote `barcode-main.zip` e alinhamento com a branch `main`. Objetivo: modernizar a engenharia sem alterar o layout original do site.

## Diagnóstico

### Crítico
- A persistência do inventário depende do Google Sheets e reescreve o intervalo A:E. O código já confirma a gravação por leitura posterior, mas ainda existe risco de concorrência entre sessões/processos.
- O cadastro de usuários usa SHA-256 simples e possui mecanismo legado de administrador. A migração para hash de senha com salt/iterações e a revisão do fluxo de autorização por URL são prioritárias.

### Alto
- A interface e o backend possuem catálogos de tipos/setores que precisam permanecer sincronizados. A definição oficial deve ficar em uma única camada e ser consumida pela apresentação.
- A extensão `consultorio_setor_ui.py` interceptava `st.selectbox` e acrescentava campos à interface. Isso alterava o layout original e transformava `Consultório` em um texto composto, contrariando o schema canônico. Sua ativação foi removida nesta etapa.
- A interface de exclusão ainda carrega conceitos herdados do modelo antigo de colunas por tipo. A persistência atual já possui o schema canônico, mas essa área merece uma refatoração específica para exclusão por registro/patrimônio.

### Médio
- O projeto possui boa cobertura das regras de inventário, mas ainda precisa de testes específicos para autenticação, autorização, concorrência e contrato de integração com o Google Sheets.
- O workflow `system-audit.yml` possui permissões de escrita e pode alterar o código automaticamente. Isso deve ser reduzido posteriormente a correções controladas, preferencialmente com PR/branch de automação.
- A dependência do scanner via CDN está versionada, mas a estratégia de fornecimento do JavaScript pode ser fortalecida futuramente com recurso local ou política de integridade.

## Evoluções aplicadas nesta etapa

1. O roteamento voltou a usar diretamente o renderer original do inventário, removendo a interceptação específica de Consultório.
2. O arquivo auxiliar `consultorio_setor_ui.py` foi removido por ser código de apresentação fora do fluxo original e por introduzir alteração de layout/schema.
3. O diagnóstico técnico passou a ser versionado no repositório.
4. Nenhum CSS, dimensão, cor, posicionamento ou estrutura visual foi alterado nesta etapa.

## Próxima arquitetura recomendada

- **Domínio:** regras e modelos do patrimônio.
- **Persistência:** adaptador Google Sheets com contrato explícito e testes mockados.
- **Apresentação:** Streamlit somente para renderização e eventos.
- **Observabilidade:** logs estruturados, métricas de falha de gravação e rastreabilidade por operação.
- **Segurança:** PBKDF2/scrypt para senhas, tokens assinados/expiráveis para aprovação por e-mail e sessão com expiração.
- **Qualidade:** CI com lint, testes, compilação, smoke test do Streamlit e análise de segurança.
- **Dados:** rotina de saneamento/migração dos registros legados antes de novas funcionalidades.
