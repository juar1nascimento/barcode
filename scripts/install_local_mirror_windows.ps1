$ErrorActionPreference = "Stop"
$MirrorRoot = "\\172.17.27.246\t.i\02 - SUPORTE\BACKUP\Inventário gti-sesa"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Inventário GTI SESA - instalação do agente local"
Write-Host "Destino: $MirrorRoot"

if (-not (Test-Path -LiteralPath $MirrorRoot)) {
    throw "A pasta de destino não está acessível: $MirrorRoot"
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    throw "Python não encontrado no servidor local."
}

& $Python.Source -m pip install -r (Join-Path $RepoRoot "requirements.txt")

$env:INVENTARIO_MIRROR_ROOT = $MirrorRoot

Write-Host "Executando pré-validação local sem acessar o banco ou o Storage..."
& $Python.Source (Join-Path $RepoRoot "scripts\check_local_mirror.py") --local-only
if ($LASTEXITCODE -ne 0) { throw "A pré-validação local falhou. Nenhuma sincronização foi executada." }

Write-Host "Dependências e acesso ao destino verificados. O agente está pronto para a pré-validação operacional."
Write-Host "Configure DATABASE_URL (ou PGHOST/PGDATABASE/PGUSER/PGPASSWORD) e SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY somente no ambiente seguro do serviço."
