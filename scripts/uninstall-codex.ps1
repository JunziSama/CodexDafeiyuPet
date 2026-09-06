[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\dafeiyu-companion'),
    [switch]$KeepSettings
)

$ErrorActionPreference = 'Stop'
$controllerActive = Test-NetConnection -ComputerName '127.0.0.1' -Port 46837 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($controllerActive) {
    throw '请先在系统托盘右键“大肥鱼 Codex 增强桌宠”并选择“彻底退出”，然后再运行卸载。'
}
$codexDir = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'
$hooksPath = Join-Path $codexDir 'hooks.json'
if (Test-Path -LiteralPath $hooksPath -PathType Leaf) {
    $doc = Get-Content -Raw -LiteralPath $hooksPath | ConvertFrom-Json -AsHashtable
    if ($doc -is [System.Collections.IDictionary] -and $doc.hooks -is [System.Collections.IDictionary]) {
        foreach ($eventName in @($doc.hooks.Keys)) {
            $kept = @($doc.hooks[$eventName]) | Where-Object {
                $json = $_ | ConvertTo-Json -Depth 20 -Compress
                $json -notmatch 'DafeiyuCodexCompanion|dafeiyu-codex-event|invoke_hook\.ps1'
            }
            if ($kept.Count) { $doc.hooks[$eventName] = $kept } else { $doc.hooks.Remove($eventName) }
        }
        $doc | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $hooksPath -Encoding utf8
    }
}

$startupShortcut = Join-Path ([Environment]::GetFolderPath('Startup')) '大肥鱼 Codex 增强桌宠.lnk'
$manualShortcut = Join-Path ([Environment]::GetFolderPath('Programs')) '大肥鱼 Codex 增强桌宠.lnk'
foreach ($path in @($startupShortcut, $manualShortcut)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}
foreach ($taskName in @('Dafeiyu Codex Companion', 'Dafeiyu Codex Companion - Manual Open')) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
}
if (-not $KeepSettings) {
    $dataDir = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\dafeiyu-companion-data'
    if (Test-Path -LiteralPath $dataDir) { Remove-Item -LiteralPath $dataDir -Recurse -Force }
}
if (Test-Path -LiteralPath $InstallRoot) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force }

[pscustomobject]@{ Uninstalled = $true; Hooks = $hooksPath; SettingsKept = [bool]$KeepSettings }
