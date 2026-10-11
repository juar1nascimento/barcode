# Configuração segura do Google Sheets no Streamlit — GTI SESA

## Modelo recomendado

Use uma **conta de serviço Google (service account)** dedicada ao inventário. Não torne a planilha pública e não coloque credenciais no código nem no GitHub.

## 1. Credenciais no Streamlit

No painel do Streamlit Community Cloud, abra o app do inventário, entre em **Settings → Secrets** e configure os campos da conta de serviço. O código aceita uma destas formas:

- `[connections.gsheets]` com os campos da conta de serviço e `spreadsheet_id` ou `spreadsheet`;
- `[gcp_service_account]` com os campos da conta de serviço e o ID da planilha em `spreadsheet_id` (ou uma URL em `spreadsheet_url`);
- variável de ambiente `GOOGLE_SHEETS_CREDENTIALS` ou `GOOGLE_SERVICE_ACCOUNT_JSON` contendo o JSON completo da conta de serviço, e `GOOGLE_SPREADSHEET_ID` (ou `GOOGLE_SHEET_URL`).

Campos essenciais: `project_id`, `private_key`, `client_email` e `token_uri`. Nunca compartilhe esses valores no chat ou em issues.

Exemplo estrutural — substitua os valores no painel de Secrets, não neste arquivo:

```toml
[gcp_service_account]
type = "service_account"
project_id = "SEU_PROJECT_ID"
private_key_id = "SUA_PRIVATE_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
client_email = "conta-de-servico@projeto.iam.gserviceaccount.com"
client_id = "SEU_CLIENT_ID"
token_uri = "https://oauth2.googleapis.com/token"

spreadsheet_id = "ID_DA_PLANILHA"
```

## 2. Conceder acesso à planilha

1. No Google Cloud Console, habilite **Google Sheets API** e **Google Drive API** no projeto da conta de serviço.
2. Copie o valor de `client_email` diretamente dos Secrets ou do JSON da conta de serviço.
3. Na planilha do inventário, clique em **Compartilhar** e adicione esse e-mail como **Editor**.
4. Mantenha o acesso restrito aos usuários e à conta de serviço necessários. Não habilite “qualquer pessoa com o link”.
5. Reinicie/reimplante o app no Streamlit se necessário para carregar os Secrets atualizados.

## 3. Limite importante

A alteração de código só permite ler as credenciais de forma mais resiliente; ela **não concede permissão por si só**. A autorização efetiva exige a conta de serviço correta nos Secrets e o compartilhamento da planilha com o respectivo `client_email`. Não é necessário expor a chave privada para realizar o compartilhamento.

## 4. Diagnóstico sem revelar segredos

- Erro de autenticação: conferir se a chave privada está completa e se os campos pertencem à mesma conta de serviço.
- Acesso negado / planilha não encontrada: conferir o ID/URL e se o `client_email` foi compartilhado como Editor.
- API desabilitada: habilitar Google Sheets API e Google Drive API no projeto da conta de serviço.
- Nunca imprimir o JSON, a chave privada ou o conteúdo integral de `st.secrets` nos logs.
