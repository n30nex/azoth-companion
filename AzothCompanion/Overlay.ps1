param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Net.Http
Add-Type -ReferencedAssemblies System.Windows.Forms -TypeDefinition @'
using System.Windows.Forms;
public class AzothGuideForm : Form {
 protected override bool ShowWithoutActivation { get { return true; } }
 protected override CreateParams CreateParams { get { var value=base.CreateParams; value.ExStyle|=0x08000080; return value; } }
}
'@
$stateRoot = if ($env:AZOTH_COMPANION_DATA) { $env:AZOTH_COMPANION_DATA } else { Join-Path $env:LOCALAPPDATA 'AzothCompanion' }
$access = Get-Content -LiteralPath (Join-Path $stateRoot 'access.json') -Raw | ConvertFrom-Json
$form = [AzothGuideForm]::new()
$form.Text='Azoth corner guide';$form.Size=[Drawing.Size]::new(390,230)
$form.TopMost=$true;$form.ShowInTaskbar=$false;$form.StartPosition='Manual'
$form.Location=[Drawing.Point]::new(20,40)
$form.BackColor=[Drawing.ColorTranslator]::FromHtml('#D5DADD')
$label=[Windows.Forms.Label]::new();$label.Dock='Fill';$label.Padding=[Windows.Forms.Padding]::new(14)
$label.Font=[Drawing.Font]::new('Segoe UI',12);$label.Text='Waiting for the dashboard...'
$form.Controls.Add($label)
if ($CheckOnly) { $form.Dispose(); Write-Output 'Overlay controls created successfully.'; return }
$client=[Net.Http.HttpClient]::new();$client.Timeout=[TimeSpan]::FromSeconds(5)
$client.DefaultRequestHeaders.Add('Cookie','azoth_local='+$access.token)
$timer=[Windows.Forms.Timer]::new();$timer.Interval=1500
$script:pending=$null
$timer.Add_Tick({
    if ($script:pending -and $script:pending.IsCompleted) {
        try {
            $value=$script:pending.GetAwaiter().GetResult() | ConvertFrom-Json
            $live=$value.live;$guide=@($value.guide);$index=[int]$live.index
            $clock=''
            if ($live.started_ms) { $seconds=[math]::Floor(([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()-$live.started_ms)/1000);$clock=('{0}:{1:00}' -f [math]::Floor($seconds/60),($seconds%60)) }
            $message=if ($live.phase -ne 'running') {'Choose a capture in the dashboard.'} elseif ($live.disconnected) {if ($value.recovery_enabled) {'Return in progress. Wait for the world to load.'} else {'Disconnected. Select your character in the game to continue.'}} elseif ($index -ge $guide.Count) {'Checklist complete. Choose Next packet or End session & send.'} else {$guide[$index].text}
            $label.Text="AZOTH  $clock`r`n`r`n$message"
        } catch { $label.Text='Dashboard unavailable. Your recorder is separate.' }
        $script:pending=$null
    }
    if (-not $script:pending) { $script:pending=$client.GetStringAsync("http://127.0.0.1:$($access.port)/api/live") }
    @{pid=$PID;seen_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()} | ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $stateRoot 'overlay.json') -Encoding utf8
})
$timer.Start()
try { [void]$form.ShowDialog() } finally { $timer.Stop();$timer.Dispose();$client.Dispose();$form.Dispose() }
