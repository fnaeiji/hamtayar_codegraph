$ErrorActionPreference = 'Stop'
Invoke-RestMethod http://127.0.0.1:8000/api/health | ConvertTo-Json
$result = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/connection/test
$result | ConvertTo-Json
if (!$result.destination.ok -or !$result.staging.ok) { throw 'Neo4j connectivity failed' }
Invoke-RestMethod http://127.0.0.1:8000/api/diagnostics | ConvertTo-Json -Depth 5
Write-Host 'Upload a small ZIP through UI, click Index, wait for ready, then verify search/source/graph.'
