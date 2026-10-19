param([string]$GameExe, [switch]$NoLaunch)
$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
if (-not $env:AZOTH_COMPANION_DATA) { $env:AZOTH_COMPANION_DATA = Join-Path $env:LOCALAPPDATA 'AzothCompanion' }
if (-not $env:AZOTH_CAPTURE_DATA) { $env:AZOTH_CAPTURE_DATA = Join-Path $env:AZOTH_COMPANION_DATA 'recorder' }
$recorder = Join-Path $packageRoot 'AzothCapture\AzothCapture.Companion.exe'
if (-not $NoLaunch -and -not (Test-Path -LiteralPath $recorder -PathType Leaf)) { throw 'Download and extract the Windows release ZIP, or build the recorder first.' }
New-Item -ItemType Directory -Path $env:AZOTH_CAPTURE_DATA -Force | Out-Null
$settingsPath = Join-Path $env:AZOTH_CAPTURE_DATA 'settings.json'
$settings = @{}
if (Test-Path -LiteralPath $settingsPath) {
    $saved = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
    foreach ($property in $saved.PSObject.Properties) { $settings[$property.Name] = $property.Value }
}
if (-not $GameExe -and -not $settings.exe_path) {
    $steamPath = (Get-ItemProperty -LiteralPath 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue).SteamPath
    if (-not $steamPath) { $steamPath = Join-Path ${env:ProgramFiles(x86)} 'Steam' }
    $libraries = @($steamPath)
    $libraryFile = Join-Path $steamPath 'steamapps\libraryfolders.vdf'
    if (Test-Path -LiteralPath $libraryFile) {
        $vdf = Get-Content -LiteralPath $libraryFile -Raw
        foreach ($match in [regex]::Matches($vdf,'"path"\s+"([^"]+)"')) { $libraries += $match.Groups[1].Value.Replace('\\','\') }
    }
    foreach ($library in ($libraries | Select-Object -Unique)) {
        $candidate = Join-Path $library 'steamapps\common\New World\Bin64\NewWorld.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $GameExe = $candidate; break }
    }
    if (-not $GameExe -and -not $NoLaunch) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = [Windows.Forms.OpenFileDialog]::new()
        $picker.Title = 'Select New World\Bin64\NewWorld.exe'
        $picker.Filter = 'New World executable|NewWorld.exe'
        if ($picker.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) { $GameExe = $picker.FileName }
        $picker.Dispose()
    }
}
if ($GameExe) {
    $game = Get-Item -LiteralPath $GameExe
    if ($game.PSIsContainer -or $game.Name -ine 'NewWorld.exe') { throw 'Choose the installed NewWorld.exe.' }
    $settings.exe_path = $game.FullName
}
if (-not $settings.timeout) { $settings.timeout = 1200 }
$settings | ConvertTo-Json | Set-Content -LiteralPath $settingsPath -Encoding utf8
if ($NoLaunch) { Write-Output 'Profile prepared; no applications started.'; return }
$other = @(Get-Process -Name AzothCapture,AzothCapture.Dashboard,AzothCapture.Companion -ErrorAction SilentlyContinue)
if ($other.Count) {
    if ($other | Where-Object { $_.Path -ne $recorder }) { throw 'Another Azoth recorder is open. Finish that recording and close it before opening this copy.' }
    & (Join-Path $packageRoot 'AzothCompanion\Start-Companion.ps1')
} else {
    Start-Process -FilePath $recorder -WorkingDirectory (Split-Path $recorder -Parent) -WindowStyle Normal | Out-Null
}
