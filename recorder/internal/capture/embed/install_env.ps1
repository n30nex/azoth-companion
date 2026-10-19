$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$runtimeRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -and $env:GITHUB_ACTIONS -ne 'true') {
    throw 'Run Azoth as your normal Windows user, not as administrator.'
}
$lock = Get-Content -LiteralPath (Join-Path $runtimeRoot 'downloads.json') -Raw | ConvertFrom-Json
$cache = Join-Path $runtimeRoot '.downloads'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
function Get-VerifiedDownload($entry) {
    $uri = [Uri]$entry.url
    if ($uri.Scheme -ne 'https' -or $uri.Host -notin @('www.python.org','codeload.github.com','files.pythonhosted.org')) { throw 'Unapproved download host.' }
    if ($entry.sha256 -notmatch '^[a-f0-9]{64}$' -or $entry.file -notmatch '^[a-z-]+\.zip$') { throw 'Invalid download lock.' }
    $path = Join-Path $cache $entry.file
    if (-not (Test-Path -LiteralPath $path) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $entry.sha256) {
        Write-Output "Downloading $($entry.file) from $($uri.Host)..."
        $temporary = $path + '.part'
        Invoke-WebRequest -Uri $uri -OutFile $temporary -UseBasicParsing
        if ((Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash -ne $entry.sha256) { throw 'Download checksum mismatch. Nothing was executed.' }
        Move-Item -LiteralPath $temporary -Destination $path -Force
    }
    return $path
}
$pythonZip = @(Get-VerifiedDownload $lock.python)[-1]
$pythonDir = Join-Path $runtimeRoot 'python_embedded'
$python = Join-Path $pythonDir 'python.exe'
$versionFile = Join-Path $pythonDir '.azoth-python-version'
if (-not (Test-Path -LiteralPath $versionFile) -or (Get-Content -LiteralPath $versionFile -Raw).Trim() -ne $lock.python_version) {
    New-Item -ItemType Directory -Path $pythonDir -Force | Out-Null
    Expand-Archive -LiteralPath $pythonZip -DestinationPath $pythonDir -Force
    Set-Content -LiteralPath $versionFile -Value $lock.python_version -Encoding ascii
}
$site = Join-Path $pythonDir 'Lib\site-packages'
New-Item -ItemType Directory -Path $site -Force | Out-Null
$pth = @(Get-ChildItem -LiteralPath $pythonDir -Filter 'python*._pth')
if ($pth.Count -ne 1) { throw 'Unexpected Python runtime layout.' }
$stdlib = @(Get-ChildItem -LiteralPath $pythonDir -Filter 'python*.zip')
if ($stdlib.Count -ne 1) { throw 'Missing Python standard library.' }
@($stdlib[0].Name,'.','Lib\site-packages','import site') | Set-Content -LiteralPath $pth[0].FullName -Encoding ascii
$pipZip = @(Get-VerifiedDownload $lock.pip)[-1]
Expand-Archive -LiteralPath $pipZip -DestinationPath $site -Force

$engineZip = @(Get-VerifiedDownload $lock.engine)[-1]
$engineRoot = Join-Path $runtimeRoot 'Aeternum-World'
$engineCode = Join-Path $engineRoot 'Tools\nw_capture'
New-Item -ItemType Directory -Path $engineCode -Force | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($engineZip)
try {
    $prefix = 'Aeternum-World-' + $lock.engine_commit + '/'
    foreach ($entry in $archive.Entries) {
        if ($entry.FullName -eq ($prefix + 'LICENSE')) {
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,(Join-Path $engineRoot 'LICENSE'),$true)
            continue
        }
        $codePrefix = $prefix + 'Tools/nw_capture/'
        if (-not $entry.FullName.StartsWith($codePrefix) -or $entry.FullName.EndsWith('/')) { continue }
        $relative = $entry.FullName.Substring($codePrefix.Length)
        if ($relative -match '(^|/)(captures|logs|https)(/|$)' -or [IO.Path]::GetExtension($relative) -notin @('.py','.js','.txt','.md','.json','.toml')) { continue }
        $target = [IO.Path]::GetFullPath((Join-Path $engineCode $relative))
        if (-not $target.StartsWith($engineCode + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Archive path escaped the engine folder.' }
        New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target,$true)
    }
} finally { $archive.Dispose() }
$requirements = Join-Path $engineCode 'requirements.txt'
if (-not (Test-Path -LiteralPath $requirements)) { throw 'Pinned engine archive is incomplete.' }
Write-Output 'Installing pinned capture and menu-helper packages from PyPI...'
& $python -m pip --isolated install --index-url https://pypi.org/simple --disable-pip-version-check --no-warn-script-location --no-cache-dir -r $requirements -r (Join-Path $runtimeRoot 'requirements-extra.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python package installation failed. Use Install in the recorder to retry.' }
& $python -c 'import frida, cv2, numpy; from PIL import Image; print("Capture runtime verified.")'
if ($LASTEXITCODE -ne 0) { throw 'Capture runtime validation failed.' }
@{engine_commit=$lock.engine_commit;python_version=$lock.python_version;companion='0.1.0'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot '.runtime-ready.json') -Encoding utf8
Write-Output 'Runtime setup complete.'
