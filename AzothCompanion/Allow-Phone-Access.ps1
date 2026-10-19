#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$stateRoot = if ($env:AZOTH_COMPANION_DATA) { $env:AZOTH_COMPANION_DATA } else { Join-Path $env:LOCALAPPDATA 'AzothCompanion' }
$access = Get-Content -LiteralPath (Join-Path $stateRoot 'access.json') -Raw | ConvertFrom-Json
if ($access.host -eq '127.0.0.1') { throw 'Open the dashboard on one trusted Private home network first.' }
$localAddress = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -eq $access.host)
if ($localAddress.Count -ne 1 -or (Get-NetConnectionProfile -InterfaceIndex $localAddress[0].InterfaceIndex).NetworkCategory -ne 'Private') { throw 'The saved address is no longer on a Private network.' }
$remaining = [int]$localAddress[0].PrefixLength
$networkBytes = @(([Net.IPAddress]::Parse($access.host)).GetAddressBytes() | ForEach-Object {
    $bits=[Math]::Min(8,[Math]::Max(0,$remaining));$remaining-=8
    $mask=if ($bits -eq 0) {0} else {256-(1 -shl (8-$bits))}
    $_ -band $mask
})
$subnet = ($networkBytes -join '.') + '/' + $localAddress[0].PrefixLength
$python = Join-Path (Split-Path $PSScriptRoot -Parent) 'AzothCapture\python_embedded\python.exe'
$ruleName = 'AzothCompanion-LAN-' + $access.port
$existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($existing) { $existing | Remove-NetFirewallRule }
New-NetFirewallRule -Name $ruleName -DisplayName 'Azoth Companion - trusted home LAN' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $access.port -LocalAddress $access.host -RemoteAddress $subnet -Program $python -Profile Private -EdgeTraversalPolicy Block | Out-Null
Write-Output 'Phone access enabled for this application and home subnet on Private networks only.'
