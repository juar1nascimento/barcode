# Política de Segurança

## Escopo
Esta política se aplica ao código e aos componentes publicados neste repositório.

## Como reportar uma vulnerabilidade
Não publique vulnerabilidades, credenciais, tokens, chaves de API ou dados sensíveis em Issues, Pull Requests ou discussões públicas.

Para um incidente de segurança, utilize o recurso **Report a vulnerability** na aba **Security** do GitHub, quando disponível. Se esse recurso não estiver disponível, entre em contato com o proprietário do repositório por um canal privado e forneça:

- descrição do problema;
- impacto potencial;
- passos para reproduzir;
- evidências mínimas necessárias;
- sugestão de correção, se houver.

## Credenciais e segredos
Credenciais nunca devem ser armazenadas no código-fonte. Utilize os **Secrets** do GitHub/Streamlit e variáveis de ambiente apropriadas.

Se uma credencial for exposta, considere-a comprometida imediatamente e faça sua rotação/revogação antes de apenas remover o arquivo do repositório.

## Processo de tratamento
1. Confirmar e classificar o incidente.
2. Conter o acesso afetado.
3. Revogar/rotacionar credenciais comprometidas.
4. Corrigir a vulnerabilidade.
5. Validar a correção com testes e análise de segurança.
6. Registrar a causa e as ações preventivas.

## Versões suportadas
A versão mantida é a publicada no branch protegido de produção (`main`).
