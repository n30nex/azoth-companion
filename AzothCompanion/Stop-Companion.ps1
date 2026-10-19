$ErrorActionPreference = 'Stop'
$stateRoot = if ($env:AZOTH_COMPANION_DATA) { $env:AZOTH_COMPANION_DATA } else { Join-Path $env:LOCALAPPDATA 'AzothCompanion' }
$path = Join-Path $stateRoot 'running.json'
if (-not (Test-Path -LiteralPath $path)) { return }
$running = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
$serverPath = Join-Path $PSScriptRoot 'server.py'
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($running.pid)" -ErrorAction SilentlyContinue
if ($process -and $process.CommandLine -like "*$serverPath*") { Stop-Process -Id $running.pid }
Write-Output 'Dashboard stopped. Recorder and game were left running.'
