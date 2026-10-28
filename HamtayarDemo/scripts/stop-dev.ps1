$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$pidFile = "$root/runtime/dev-pids.json"
if (!(Test-Path $pidFile)) { Write-Host 'No managed processes recorded'; exit }
$record = Get-Content $pidFile | ConvertFrom-Json
foreach ($name in @('frontend','backend')) {
    $process = Get-Process -Id $record.$name -ErrorAction SilentlyContinue
    $startProperty = $name + 'Start'
    if ($process -and $process.StartTime.ToUniversalTime().ToString('o') -eq $record.$startProperty) {
        taskkill /PID $process.Id /T /F | Out-Null
    }
}
Remove-Item $pidFile
