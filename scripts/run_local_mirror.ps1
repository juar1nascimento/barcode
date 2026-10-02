$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:INVENTARIO_MIRROR_ROOT = "\\172.17.27.246\t.i\02 - SUPORTE\BACKUP\Inventário gti-sesa"

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { throw "Python não encontrado." }

& $Python.Source (Join-Path $RepoRoot "scripts\check_local_mirror.py")
if ($LASTEXITCODE -ne 0) { throw "Pré-validação operacional falhou. Sincronização bloqueada." }

& $Python.Source (Join-Path $RepoRoot "scripts\mirror_local_server.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
