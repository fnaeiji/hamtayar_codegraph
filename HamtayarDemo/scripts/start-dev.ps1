$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force "$root/runtime" | Out-Null
$pidFile = "$root/runtime/dev-pids.json"
if (Test-Path $pidFile) { throw 'Run stop-dev.ps1 before starting again' }
$backend = Start-Process -FilePath "$root/backend/.venv/Scripts/python.exe" -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory "$root/backend" -PassThru
try {
    $frontend = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','npm run dev -- --strictPort' -WorkingDirectory "$root/frontend" -PassThru
    @{ backend=$backend.Id; frontend=$frontend.Id; backendStart=$backend.StartTime.ToUniversalTime().ToString('o'); frontendStart=$frontend.StartTime.ToUniversalTime().ToString('o') } | ConvertTo-Json | Set-Content $pidFile
} catch { Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue; throw }
Write-Host 'UI: http://127.0.0.1:5173 | API: http://127.0.0.1:8000/docs'
