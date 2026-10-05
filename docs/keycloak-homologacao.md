# GTI-SESA — Desenho de homologação Keycloak/OIDC

**Status:** somente homologação; não autoriza ativação em produção.  
**Branch:** `homolog/keycloak-oidc`

## 1. Objetivo

Substituir progressivamente a administração de identidade, senha, recuperação e sessão do login local por Keycloak/OIDC, sem alterar o layout atual do login em produção e sem interromper o mecanismo local durante a homologação.

O Keycloak será a autoridade de identidade. O GTI-SESA continuará responsável pelas regras funcionais do sistema e pelo acesso aos dados.

## 2. Arquitetura-alvo

```
Usuário
  ↓ HTTPS
Keycloak
  ├─ identidade
  ├─ senha
  ├─ recuperação de senha
  ├─ MFA/políticas
  └─ sessão/logout
        ↓ OIDC
GTI-SESA / Streamlit
  ├─ valida sessão OIDC
  ├─ recebe claims
  ├─ aplica autorização funcional
  └─ acessa Supabase/Storage/integrações
```

O aplicativo **não deve receber nem armazenar a senha do usuário** no fluxo OIDC.

## 3. Realm

Nome proposto:

`gti-sesa`

Regras:
- realm dedicado ao GTI-SESA;
- não reutilizar o realm administrativo `master` para usuários da aplicação;
- administração do realm restrita a contas administrativas próprias;
- MFA e políticas de senha devem ser configuradas no realm;
- exportação/backup do realm deve fazer parte da rotina de recuperação.

## 4. Cliente OIDC

Cliente proposto:

`gti-sesa-streamlit`

Tipo:
- cliente OIDC confidencial;
- fluxo Authorization Code;
- client secret somente em Secrets/variáveis protegidas do ambiente;
- nenhum secret no GitHub, código-fonte ou documentação.

Redirect URI de homologação:
- usar exclusivamente a URL real da implantação de homologação;
- permitir somente a rota `/oauth2callback`;
- não usar curingas amplos.

Redirect URI de produção:
- somente será cadastrada após aprovação do gate de homologação e publicação controlada.

Web origins:
- somente a origem HTTPS real do aplicativo;
- nenhuma origem `*`.

## 5. Roles

Roles mínimas do realm:

- `usuario`: acesso operacional normal;
- `admin`: funções administrativas.

Regra crítica:

> Ser administrador não será determinado pelo endereço de e-mail.

O aplicativo deve reconhecer privilégio administrativo somente por role/claim explícito emitido pelo Keycloak.

O adaptador atual já suporta `roles` e, como compatibilidade, `realm_access.roles`.

## 6. Claims

Claims mínimos esperados:

- `sub`: identificador estável do usuário;
- `email`: e-mail;
- `preferred_username`: identificador de login;
- `name`: nome;
- `roles`: roles autorizadas para o aplicativo.

O `sub` deve ser tratado como identificador técnico estável. O e-mail não deve ser usado como chave permanente de identidade.

## 7. Migração dos usuários atuais

Não importar cegamente os hashes PBKDF2 existentes para o Keycloak.

Estratégia segura:

1. preservar `gti_auth_usuarios` durante toda a homologação;
2. criar no Keycloak as identidades correspondentes;
3. atribuir `usuario` ou `admin` conforme autorização previamente validada;
4. exigir primeiro acesso/redefinição de senha no Keycloak;
5. validar login e recuperação;
6. somente depois definir a janela de migração;
7. manter rollback para o login local até a aprovação final.

Nenhuma senha existente deve ser exposta, copiada para chat ou registrada em arquivo de migração.

## 8. Recuperação de acesso

No estado-alvo:

- recuperação de senha será executada pelo Keycloak;
- SMTP será configurado no Keycloak;
- links de recuperação terão validade limitada;
- recuperação deverá invalidar sessões/credenciais conforme política definida;
- o GTI-SESA não enviará senha por e-mail.

A recuperação local atual permanece como contingência durante a homologação.

## 9. Sessão e logout

Critérios mínimos:

- sessão OIDC obrigatória antes de acessar qualquer página protegida;
- logout deve encerrar a sessão do aplicativo e do provedor conforme o fluxo suportado;
- acesso direto a páginas internas sem sessão deve ser bloqueado;
- expiração de sessão deve retornar o usuário ao fluxo de autenticação;
- não armazenar tokens de acesso em arquivos ou banco de dados da aplicação.

## 10. Infraestrutura obrigatória antes do teste E2E

Keycloak não será hospedado em GitHub Actions nem dentro do Streamlit.

Antes do teste real devem existir:

- hostname HTTPS estável;
- TLS válido;
- servidor persistente;
- banco de dados persistente e suportado;
- backup e restauração testados;
- SMTP funcional;
- proteção da console administrativa;
- monitoramento e logs;
- política de atualização;
- controle de acesso à infraestrutura;
- reverse proxy quando aplicável;
- portas administrativas não expostas desnecessariamente à Internet.

## 11. Secrets

Nunca versionar:

- client secret;
- cookie secret;
- credenciais do banco do Keycloak;
- credenciais SMTP;
- chaves de administração;
- tokens;
- senhas de usuários.

No Streamlit, os valores OIDC ficarão exclusivamente em Secrets.

## 12. Rollback

Durante a homologação:

- `[auth].homologacao=true` ativa somente o caminho OIDC isolado;
- `[auth].homologacao=false` ou ausência da configuração mantém o login local;
- `main` continua sendo a referência de produção;
- `gti_auth_usuarios` não será apagada durante a migração.

Qualquer falha de autenticação, autorização, recuperação, logout ou sessão bloqueia a promoção.

## 13. Critérios de aceite do E2E

O gate somente poderá ser aprovado quando todos os testes abaixo forem demonstrados:

1. usuário normal consegue autenticar;
2. administrador consegue autenticar;
3. usuário normal não recebe role `admin`;
4. administrador recebe role `admin`;
5. usuário sem role válida não recebe privilégio administrativo;
6. acesso direto sem sessão é bloqueado;
7. logout funciona;
8. expiração de sessão funciona;
9. recuperação de senha funciona;
10. e-mail de recuperação chega;
11. senha antiga deixa de funcionar após redefinição;
12. senha nova funciona;
13. MFA/políticas configuradas funcionam, se habilitadas;
14. nenhum segredo aparece em logs;
15. nenhuma senha passa pelo Streamlit;
16. funcionalidades de inventário permanecem operacionais;
17. fotos/Storage e demais integrações não perdem autorização;
18. rollback para login local funciona.

## 14. Condição de promoção

**Não promover para `main`** enquanto não houver:

- Keycloak persistente e HTTPS;
- realm configurado;
- cliente OIDC configurado;
- roles e claims validados;
- SMTP testado;
- recuperação testada;
- logout testado;
- autorização testada;
- segurança revisada;
- teste E2E aprovado;
- plano de rollback validado.

## 15. Estado atual

A branch de homologação contém apenas o adaptador OIDC e a chave reversível de homologação.

Produção continua no login local.

Não houve alteração de:
- layout do login local;
- usuários da produção;
- senhas;
- Supabase Auth;
- tabela `gti_auth_usuarios`;
- Secrets do Streamlit;
- infraestrutura de produção.
