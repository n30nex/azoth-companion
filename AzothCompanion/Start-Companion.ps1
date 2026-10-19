param([switch]$NoOpen,[string]$LanAddress,[int]$Port=8877)
$ErrorActionPreference = 'Stop'
if (-not $env:AZOTH_COMPANION_DATA) { $env:AZOTH_COMPANION_DATA = Join-Path $env:LOCALAPPDATA 'AzothCompanion' }
if (-not $env:AZOTH_CAPTURE_DATA) { $env:AZOTH_CAPTURE_DATA = Join-Path $env:AZOTH_COMPANION_DATA 'recorder' }
$stateRoot = $env:AZOTH_COMPANION_DATA
$serverPath = Join-Path $PSScriptRoot 'server.py'
$python = Join-Path (Split-Path $PSScriptRoot -Parent) 'AzothCapture\python_embedded\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Open Start-Azoth.cmd and let the recorder finish its first-time setup.' }
$listenAddress = '127.0.0.1'; $prefixLength = 32
$privateNetworks = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object NetworkCategory -eq 'Private')
$networks = @(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' -and $_.InterfaceIndex -in $privateNetworks.InterfaceIndex })
if ($LanAddress) {
    $networks = @($networks | Where-Object { $_.IPv4Address.IPAddress -contains $LanAddress })
    if ($networks.Count -ne 1) { throw 'Choose a local IPv4 address on one trusted Private network.' }
}
if ($networks.Count -eq 1) {
    $listenAddress = [string]$networks[0].IPv4Address.IPAddress
    $prefixLength = $networks[0].IPv4Address.PrefixLength
}
$listener = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Where-Object LocalAddress -eq '127.0.0.1')
if ($listener.Count) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
    if ($owner.CommandLine -notlike "*$serverPath*") { throw "Port $Port belongs to another application or Azoth installation." }
} else {
    New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    $arguments = '"{0}" --host {1} --prefix {2} --port {3}' -f $serverPath,$listenAddress,$prefixLength,$Port
    Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $stateRoot 'server-output.log') -RedirectStandardError (Join-Path $stateRoot 'server-error.log') | Out-Null
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Where-Object LocalAddress -eq '127.0.0.1') { break }
    }
}
$url = "http://127.0.0.1:$Port"
$response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
if ($response.StatusCode -ne 200) { throw 'The dashboard did not start.' }
if (-not $NoOpen) { Start-Process $url }
Write-Output $url
