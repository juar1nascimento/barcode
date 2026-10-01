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

## Controles obrigatórios de produção

### GitHub
O repositório de produção deve ser **Private** quando o código, configurações ou dados forem restritos.
O branch `main` deve ser protegido com:
- pull request obrigatório;
- pelo menos 1 aprovação do proprietário;
- status checks obrigatórios (testes, auditoria e CodeQL);
- proibição de push direto;
- proibição de force-push e exclusão do branch;
- CODEOWNERS obrigatório para arquivos de produção e segurança;
- MFA/2FA habilitado na conta do proprietário;
- Secret Scanning/Push Protection habilitados quando disponíveis.

Esses controles são administrativos do GitHub e devem ser conferidos pelo proprietário no painel do repositório.

### Streamlit
As credenciais devem permanecer exclusivamente em **Secrets**. O aplicativo não deve exibir valores de Secrets nem gravá-los em logs.
O ambiente de produção deve usar HTTPS e acesso privado/restrito quando o projeto exigir confidencialidade. O controle de acesso do Streamlit Community Cloud herda as permissões do GitHub; portanto, o repositório e suas permissões devem ser protegidos no GitHub.

### Supabase
As tabelas operacionais e filas de integração devem permanecer inacessíveis aos papéis `anon` e `authenticated` quando o sistema utiliza conexão PostgreSQL privada.
Buckets que contenham fotografias patrimoniais devem ser privados. O acesso visual deve ocorrer por URL assinada e temporária.
Chaves `service_role` nunca podem ser usadas no navegador ou gravadas no repositório.

### Inicialização do administrador
A conta administrativa inicial não possui senha padrão no código. Quando necessário, o proprietário deve fornecer `[email].admin_email` e um `[email].admin_password_hash` em Secrets, usando um hash PBKDF2 gerado pelo sistema. Nunca registrar senha em texto puro.

Para o worker de sincronização de fotos, o GitHub Actions deve receber a chave exclusivamente por `GTI_SUPABASE_SERVICE_ROLE_KEY`; ela nunca deve ser escrita em YAML, código ou logs.
