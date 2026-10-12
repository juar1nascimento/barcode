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


## Linux/Ubuntu — instalação automática não destrutiva

O destino padrão Linux deste projeto é `$HOME/GTI-SESA/Fotos`. O instalador cria um ambiente Python isolado e um timer de usuário do systemd para executar o espelhamento a cada 15 minutos. Ele reaproveita `scripts/download_drive_photos_local.py`, que usa escopo Google Drive somente leitura e percorre a raiz configurada, preservando a hierarquia das pastas.

### Instalação no computador Ubuntu

Na raiz do repositório `~/barcode-download-worker` (ou na pasta local em que o repositório foi clonado):

```bash
bash scripts/install_local_photo_mirror_linux.sh
```

O instalador espera a credencial JSON em `~/.config/gti-sesa/drive-reader.json`. Se ela ainda não estiver nessa localização, copie o arquivo de credencial existente para esse caminho localmente, com permissões restritas; nunca o coloque no GitHub ou no chat. O instalador cria `~/.config/gti-sesa/local-photo-mirror.env` com a raiz do Drive já definida no projeto e o destino `$HOME/GTI-SESA/Fotos`, instala as dependências numa `.venv` e executa uma simulação. A primeira execução não ativa o timer.

Depois de revisar a prévia e confirmar que a conta de serviço tem acesso de leitura à pasta do Drive, habilite a rotina:

```bash
bash scripts/install_local_photo_mirror_linux.sh --enable
```

### Operação e logs

```bash
systemctl --user status gti-sesa-photo-mirror.timer
journalctl --user -u gti-sesa-photo-mirror.service -n 100 --no-pager
```

O timer roda a cada 15 minutos enquanto a sessão de usuário/sistema permitir os timers de usuário. Para parar a automação:

```bash
systemctl --user disable --now gti-sesa-photo-mirror.timer
```

### Garantias e limites

- Somente arquivos com MIME type `image/*` são baixados.
- A credencial usa escopo `drive.readonly`; o worker não move, renomeia nem exclui nada no Drive.
- Cada download vai primeiro para um arquivo temporário e só é finalizado após validação de tamanho e MD5 quando o Drive disponibiliza esse hash.
- Se já existir um arquivo local com o mesmo caminho, mas conteúdo/tamanho diferente, a rotina agora preserva o arquivo local e registra `CONFLITO LOCAL`; não o sobrescreve nem apaga.
- Arquivos locais não são removidos automaticamente.
- O computador precisa estar ligado, com rede disponível, e a conta de serviço deve ter acesso à pasta raiz do Drive.
- O chat pode preparar e versionar os componentes, mas não consegue instalar o serviço, acessar a credencial privada nem gravar diretamente no disco do Ubuntu. A instalação final precisa ser executada no próprio computador.

## Limite operacional

O código está preparado no repositório, mas a execução real depende do computador de destino, da credencial local e do acesso de leitura à pasta raiz. Não se pode afirmar que fotos já foram baixadas sem um log produzido no próprio computador.
