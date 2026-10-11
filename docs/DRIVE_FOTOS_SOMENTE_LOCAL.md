# GTI SESA — baixar somente fotos do Google Drive para o computador local

Este procedimento é separado do espelhamento do inventário e tem escopo estrito: baixar somente arquivos cujo MIME type começa com \`image/\`. Não baixa planilhas, PDFs, documentos ou outros tipos. Não altera nem exclui arquivos da nuvem, e nunca apaga arquivos locais.

## O que já existia e onde paramos

- O projeto já possui o agente de espelhamento local e a fila de fotos.
- PR #39 foi integrado à \`main\`, mas PR #40 (download direto pela API e canário de uma foto) foi integrado somente à branch \`feat/local-drive-mirror-worker\`, não à \`main\`.
- O worker da fila original tem um fluxo \`--live\` que pode excluir a origem do Drive depois de verificar a cópia. **Não use \`--live\` para este objetivo de cópia/backup.**
- Esta ferramenta é deliberadamente independente da fila: ela percorre a pasta raiz configurada e baixa apenas imagens, preservando as subpastas Unidade → Patrimônio.

## Pré-requisitos no computador que receberá as fotos

- Windows com Python 3.12+.
- A pasta de destino deve ser um caminho local com espaço suficiente, por exemplo \`C:\\GTI-SESA\\Fotos\`.
- A conta de serviço Google deve ter acesso de leitura à pasta raiz e às subpastas. Não torne o Drive público.
- O JSON da conta de serviço fica fora do repositório, com acesso restrito ao usuário/serviço que executa a sincronização.

## Configuração de ambiente (PowerShell)

Na sessão do PowerShell que executará a sincronização, configure os valores reais localmente; não os coloque no GitHub:

\`\`\`powershell
$env:GOOGLE_SERVICE_ACCOUNT_FILE = "C:\\caminho-seguro\\gti-drive-reader.json"
$env:GOOGLE_DRIVE_ROOT_ID = "ID_DA_PASTA_RAIZ_DO_INVENTARIO"
$env:LOCAL_PHOTOS_ROOT = "C:\\GTI-SESA\\Fotos"
python -m pip install google-api-python-client google-auth
\`\`\`

Se a conta de serviço já estiver disponível como JSON em um gerenciador seguro, também pode ser usada a variável \`GOOGLE_SERVICE_ACCOUNT_JSON\` em vez do caminho do arquivo. Nunca compartilhe o conteúdo do JSON no chat ou no repositório.

## Executar primeiro em simulação

Na raiz do repositório:

\`\`\`powershell
python scripts\\download_drive_photos_local.py
\`\`\`

A simulação lista o que seria baixado e não grava as imagens.

## Baixar somente as fotos

Depois de conferir a pasta de origem e o destino local:

\`\`\`powershell
python scripts\\download_drive_photos_local.py --download
\`\`\`

O download usa arquivos temporários, valida tamanho e MD5 quando o Drive fornece esse hash, e só então troca o arquivo de destino. Arquivos já iguais são ignorados. Arquivos que não são imagens nunca são baixados. Não há exclusão da nuvem nem remoção de arquivos locais.

## Sincronização recorrente

Depois que a primeira execução for validada no computador de destino, a mesma linha com \`--download\` pode ser agendada no Agendador de Tarefas do Windows. Execute com uma conta de sistema que tenha acesso ao JSON e à pasta local; mantenha as credenciais fora do repositório. Não configure a tarefa para executar o worker de fila com \`--live\`.

## Limite operacional

O código e a configuração podem ser preparados pelo repositório, mas a execução no computador local exige que o script seja instalado/acionado nesse computador e que a conta de serviço tenha leitura real da pasta raiz. Não é possível afirmar que as fotos já foram baixadas até existir um log da execução no computador de destino.
