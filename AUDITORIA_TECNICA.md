# Auditoria técnica — Sistema de Inventários GTI-SESA

## Escopo

Auditoria do pacote `barcode-main.zip` e alinhamento com a branch `main` do projeto. O objetivo desta etapa é modernizar a engenharia sem alterar o layout original do site.

## Diagnóstico

### Crítico
- A persistência do inventário depende do Google Sheets e reescreve o intervalo A:E. O código já faz confirmação por leitura posterior, mas ainda existe risco de concorrência entre sessões/processos.
- O cadastro de usuários usa SHA-256 simples e possui mecanismo legado de administrador. A migração para hash de senha com salt/iterações e a revisão do fluxo de autorização por URL são prioritárias.

### Alto
- Havia duas fontes de verdade para os catálogos de tipos/setores: backend e interface. Isso aumenta risco de divergência.
- A extensão `consultorio_setor_ui.py` interceptava `st.selectbox` e acrescentava campos à interface. Além de alterar o layout original, transformava `Consultório` em um texto composto, contrariando o catálogo canônico do inventário.
- A interface de exclusão ainda carrega conceitos herdados do modelo antigo de colunas por tipo. A persistência atual já possui o schema canônico, mas essa área merece uma refatoração específica para exclusão por registro/patrimônio.

### Médio
- O projeto possui boa cobertura das regras de inventário, mas ainda precisa de testes específicos para autenticação, autorização, concorrência e contrato de integração com o Google Sheets.
- O workflow `system-audit.yml` possui permissões de escrita e pode alterar o código automaticamente. Isso deve ser reduzido posteriormente a correções controladas, preferencialmente com PR/branch de automação.
- A dependência do scanner via CDN está versionada, mas a estratégia de fornecimento do JavaScript pode ser fortalecida futuramente com recurso local ou política de integridade.

## Evoluções aplicadas nesta etapa

1. Catálogo oficial de tipos passou a ter uma única fonte no backend e a interface reutiliza essa definição.
2. Catálogo oficial de setores passou a ser reutilizado diretamente pelo inventário, eliminando duplicação.
3. A ativação da extensão específica de Consultório foi removida do roteamento. O setor `Consultório` volta a ser tratado pelo fluxo original, preservando a interface e o schema canônico.
4. O arquivo auxiliar de interceptação de interface foi removido por ser código morto após a correção do roteamento.
5. O diagnóstico foi registrado no repositório para orientar a próxima evolução.

## Próxima arquitetura recomendada

- **Camada de domínio:** regras e modelos do patrimônio.
- **Camada de persistência:** adaptador Google Sheets com contrato explícito e testes mockados.
- **Camada de apresentação:** Streamlit apenas para renderização e eventos.
- **Observabilidade:** logs estruturados, métricas de falha de gravação e rastreabilidade por operação.
- **Segurança:** PBKDF2/scrypt para senhas, tokens assinados/expiráveis para aprovação por e-mail e sessão com expiração.
- **Qualidade:** CI com lint, testes, compilação, smoke test do Streamlit e análise de segurança.
- **Dados:** rotina de saneamento/migração dos registros legados antes de qualquer expansão funcional.

## Regra de preservação visual

Nenhuma alteração de CSS, dimensões, cores, posicionamento ou estrutura visual do login/inventário é parte desta evolução. As mudanças desta etapa são de arquitetura, organização de código e governança técnica.
