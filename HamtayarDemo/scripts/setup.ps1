$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path backend/.venv/Scripts/python.exe)) {
    py -3.12 -m venv backend/.venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 environment creation failed' }
}
& "$root/backend/.venv/Scripts/python.exe" -m pip install -e "$root/backend[test]"
if ($LASTEXITCODE -ne 0) { throw 'Backend installation failed' }
Push-Location frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
Write-Host 'Edit HamtayarDemo/.env, then run docker compose up -d and scripts/start-dev.ps1'
