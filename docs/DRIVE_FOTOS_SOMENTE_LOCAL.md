# GTI SESA — baixar somente fotos do Google Drive para o computador local

Esta ferramenta é separada do espelhamento do inventário e baixa exclusivamente arquivos cujo MIME type começa com `image/`. Não baixa planilhas, PDFs ou outros tipos. Não altera nem exclui arquivos na nuvem e nunca apaga arquivos locais.

## Ponto recuperado do histórico

- PR #39 adicionou a base do agente de espelhamento local.
- PR #40 adicionou download direto pela API e um modo de canário na branch de desenvolvimento do worker.
- O worker original possui um modo operacional que pode excluir a origem no Drive depois de validar a cópia. **Não use esse worker em modo `--live` para fazer backup de fotos.**
- Este script é independente: percorre a pasta raiz configurada e preserva as subpastas Unidade → Patrimônio, baixando apenas imagens.

## Pré-requisitos no computador de destino

- Windows com Python 3.12 ou superior.
- Espaço local suficiente, por exemplo em `C:\GTI-SESA\Fotos`.
- A conta de serviço Google precisa ter acesso de leitura à pasta raiz e às subpastas. Não torne a pasta pública.
- O JSON da conta de serviço deve ficar fora do repositório, com acesso restrito.

## Configuração no PowerShell

Na sessão que executará a sincronização, defina os valores reais localmente; não os publique no GitHub:

```powershell
$env:GOOGLE_SERVICE_ACCOUNT_FILE = "C:\caminho-seguro\gti-drive-reader.json"
$env:GOOGLE_DRIVE_ROOT_ID = "ID_DA_PASTA_RAIZ_DO_INVENTARIO"
$env:LOCAL_PHOTOS_ROOT = "C:\GTI-SESA\Fotos"
python -m pip install google-api-python-client google-auth
```

Se a credencial já estiver disponível em um gerenciador seguro como JSON, pode usar `GOOGLE_SERVICE_ACCOUNT_JSON` em vez do caminho do arquivo. Nunca compartilhe o conteúdo da credencial no chat ou no repositório.

## 1. Simulação (não baixa)

Na raiz do repositório:

```powershell
python scripts\download_drive_photos_local.py
```

A simulação lista as imagens que seriam baixadas e identifica as já existentes e iguais no computador.

## 2. Download efetivo de fotos

Depois de conferir a pasta de origem e o destino:

```powershell
python scripts\download_drive_photos_local.py --download
```

O script baixa para um arquivo temporário, valida tamanho e MD5 quando o Drive fornece esse hash, e só então substitui o destino. Arquivos já iguais são ignorados. Outros tipos de arquivo não são baixados. Nenhum arquivo da nuvem é alterado ou excluído.

## 3. Sincronização recorrente

Depois que a primeira execução for validada no computador, a mesma linha com `--download` pode ser agendada pelo Agendador de Tarefas do Windows. A tarefa precisa rodar com uma conta que consiga ler a credencial e gravar na pasta local. Não agende o worker original com `--live`.

## Limite operacional

O código está preparado no repositório, mas a execução real depende do computador de destino, da credencial local e do acesso de leitura à pasta raiz. Não se pode afirmar que fotos já foram baixadas sem um log produzido no próprio computador.
