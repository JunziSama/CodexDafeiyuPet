[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\dafeiyu-companion'),
    [string]$PythonRoot = '',
    [switch]$ResetSettings,
    [switch]$SkipLaunch
)

$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$installRootFull = [IO.Path]::GetFullPath($InstallRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$packagePythonRoot = Join-Path $sourceRoot 'portable-python'
$usePackagedPython = $false
if (-not $PythonRoot) {
    if (Test-Path -LiteralPath (Join-Path $packagePythonRoot 'python.exe') -PathType Leaf) {
        $PythonRoot = $packagePythonRoot
        $usePackagedPython = $true
    } else {
        $runtimeBase = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes'
        $detected = Get-ChildItem -LiteralPath $runtimeBase -Recurse -File -Filter 'pythonw.exe' -ErrorAction SilentlyContinue |
            Where-Object { $_.DirectoryName -like '*codex-primary-runtime*dependencies*python' } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($detected) { $PythonRoot = $detected.DirectoryName }
    }
}
if (-not $PythonRoot) {
    throw 'Python runtime not found. Use the offline package or pass -PythonRoot explicitly.'
}
$sourcePythonExe = Join-Path $PythonRoot 'python.exe'
$sourcePythonwExe = Join-Path $PythonRoot 'pythonw.exe'
if (-not (Test-Path -LiteralPath $sourcePythonExe -PathType Leaf)) { throw "Python runtime not found: $sourcePythonExe" }
if (-not (Test-Path -LiteralPath $sourcePythonwExe -PathType Leaf)) { throw "Windowless Python runtime not found: $sourcePythonwExe" }

$residentTaskName = 'Dafeiyu Codex Companion'
$manualTaskName = 'Dafeiyu Codex Companion - Manual Open'
foreach ($taskName in @($residentTaskName, $manualTaskName)) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Milliseconds 500

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$copyNames = @('controller', 'hooks', 'runtime', 'scripts', 'config', 'LICENSE')
if ($usePackagedPython) { $copyNames += 'portable-python' }
foreach ($name in $copyNames) {
    $source = Join-Path $sourceRoot $name
    if (-not (Test-Path -LiteralPath $source)) { continue }
    $destination = Join-Path $InstallRoot $name
    $destinationFull = [IO.Path]::GetFullPath($destination)
    if (-not $destinationFull.StartsWith($installRootFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace a path outside InstallRoot: $destinationFull"
    }
    if (Test-Path -LiteralPath $destination) {
        Remove-Item -LiteralPath $destination -Recurse -Force
    }
    Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
}
# Never ship interpreter caches from the development tree. They can otherwise
# preserve an earlier controller implementation when timestamps happen to match.
Get-ChildItem -LiteralPath $InstallRoot -Directory -Filter '__pycache__' -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
    $cacheFull = [IO.Path]::GetFullPath($_.FullName)
    if (-not $cacheFull.StartsWith($installRootFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a cache outside InstallRoot: $cacheFull"
    }
    Remove-Item -LiteralPath $cacheFull -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $sourceRoot 'README-CODEX.md') -Destination (Join-Path $InstallRoot 'README.md') -Force

# Create a manifest for the installed subset. The package manifest covers the
# complete offline ZIP (including development files), while the installed tree
# intentionally contains only runtime components.
$installedManifest = Join-Path $InstallRoot 'PACKAGE-MANIFEST.sha256'
if (Test-Path -LiteralPath $installedManifest) { Remove-Item -LiteralPath $installedManifest -Force }
$installedManifestLines = Get-ChildItem -LiteralPath $InstallRoot -Recurse -File |
    Where-Object { $_.FullName -ne $installedManifest } |
    Sort-Object FullName |
    ForEach-Object {
        $relative = [IO.Path]::GetRelativePath($InstallRoot, $_.FullName).Replace('\', '/')
        "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash, $relative
    }
[IO.File]::WriteAllLines($installedManifest, $installedManifestLines, [Text.UTF8Encoding]::new($false))

$installedPythonRoot = if ($usePackagedPython) { Join-Path $InstallRoot 'portable-python' } else { $PythonRoot }
$pythonExe = Join-Path $installedPythonRoot 'python.exe'
$pythonwExe = Join-Path $installedPythonRoot 'pythonw.exe'

$codexDir = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'
$dataDir = Join-Path $codexDir 'dafeiyu-companion-data'
$legacyDataDir = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'codex-dafeiyu-enhanced'
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$configPath = Join-Path $dataDir 'controller.json'
$config = [ordered]@{
    version = 3
    enhanced_enabled = $true
    auto_accompany = $true
    visible = $true
    bridge_host = '127.0.0.1'
    bridge_port = 46837
    process_poll_ms = 1500
    python_executable = $pythonExe
    hook_event_count = 0
    hook_last_event = ''
    hook_last_received_at = 0
    hook_last_model_slug = ''
    hook_last_model_label = 'Codex'
    hook_last_applied = $false
    hook_ignored_count = 0
}
$preservedConfigPath = $configPath
if (-not (Test-Path -LiteralPath $preservedConfigPath -PathType Leaf)) {
    $preservedConfigPath = Join-Path $legacyDataDir 'controller.json'
}
if (Test-Path -LiteralPath $preservedConfigPath -PathType Leaf) {
    try {
        $old = Get-Content -Raw -LiteralPath $preservedConfigPath | ConvertFrom-Json
        foreach ($key in @(
            'visible', 'bridge_port', 'process_poll_ms',
            'hook_event_count', 'hook_last_event', 'hook_last_received_at',
            'hook_last_model_slug', 'hook_last_model_label',
            'hook_last_applied', 'hook_ignored_count'
        )) {
            if ($null -ne $old.$key) { $config[$key] = $old.$key }
        }
        if (
            -not ($old.PSObject.Properties.Name -contains 'hook_last_applied') -and
            [int64]$config.hook_last_received_at -gt 0
        ) {
            # Version 2 applied every accepted hook. Preserve the meaning of
            # the last event until a version 3 event refreshes this status.
            $config.hook_last_applied = $true
        }
    } catch {}
}
$config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configPath -Encoding utf8
$petConfigPath = Join-Path $dataDir 'config.json'
$legacyPetConfigPath = Join-Path $legacyDataDir 'config.json'
if ($ResetSettings -or -not (Test-Path -LiteralPath $petConfigPath -PathType Leaf)) {
    $safePreferences = Join-Path $sourceRoot 'config\safe-preferences.json'
    if (Test-Path -LiteralPath $safePreferences -PathType Leaf) {
        Copy-Item -LiteralPath $safePreferences -Destination $petConfigPath -Force
    } elseif (Test-Path -LiteralPath $legacyPetConfigPath -PathType Leaf) {
        Copy-Item -LiteralPath $legacyPetConfigPath -Destination $petConfigPath -Force
    }
}

$hookScript = Join-Path $InstallRoot 'hooks\invoke_hook.ps1'
$hookCommand = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$hookScript`" -DataDir `"$dataDir`""
$handler = [ordered]@{
    type = 'command'
    command = 'python3 ~/.codex/hooks/dafeiyu-codex-event.py'
    commandWindows = $hookCommand
    async = $true
    timeout = 2
}
$petEvents = [ordered]@{
    SessionStart = @([ordered]@{ matcher = 'startup|resume|clear|compact'; hooks = @($handler) })
    UserPromptSubmit = @([ordered]@{ hooks = @($handler) })
    PreToolUse = @([ordered]@{ matcher = '*'; hooks = @($handler) })
    PostToolUse = @([ordered]@{ matcher = '*'; hooks = @($handler) })
    PermissionRequest = @([ordered]@{ matcher = '*'; hooks = @($handler) })
    Stop = @([ordered]@{ hooks = @($handler) })
}
New-Item -ItemType Directory -Force -Path $codexDir | Out-Null
$hooksPath = Join-Path $codexDir 'hooks.json'
$hooksDoc = [ordered]@{ description = 'User lifecycle hooks'; hooks = [ordered]@{} }
if (Test-Path -LiteralPath $hooksPath -PathType Leaf) {
    $parsed = Get-Content -Raw -LiteralPath $hooksPath | ConvertFrom-Json -AsHashtable
    if ($parsed -is [System.Collections.IDictionary]) { $hooksDoc = $parsed }
    if (-not $hooksDoc.Contains('hooks') -or $hooksDoc.hooks -isnot [System.Collections.IDictionary]) {
        $hooksDoc.hooks = [ordered]@{}
    }
}
$hooksBefore = $hooksDoc | ConvertTo-Json -Depth 20 -Compress
foreach ($eventName in $petEvents.Keys) {
    $existing = @($hooksDoc.hooks[$eventName]) | Where-Object {
        if ($null -eq $_) { return $false }
        $json = $_ | ConvertTo-Json -Depth 20 -Compress
        return $json -notmatch 'DafeiyuCodexCompanion|dafeiyu-codex-event|invoke_hook\.ps1'
    }
    $hooksDoc.hooks[$eventName] = @($existing) + @($petEvents[$eventName])
}
$hooksAfter = $hooksDoc | ConvertTo-Json -Depth 20 -Compress
if ($hooksAfter -ne $hooksBefore -or -not (Test-Path -LiteralPath $hooksPath -PathType Leaf)) {
    $hooksDoc | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $hooksPath -Encoding utf8
}

$controllerMain = Join-Path $InstallRoot 'controller\main.py'
# Older packages used WScript/VBS as a windowless launcher.  A shortcut can
# target pythonw.exe directly, which removes an unnecessary failure point.
foreach ($obsoleteLauncher in @('start-controller.vbs', 'open-controller.vbs')) {
    $obsoletePath = Join-Path $InstallRoot $obsoleteLauncher
    if (Test-Path -LiteralPath $obsoletePath) {
        Remove-Item -LiteralPath $obsoletePath -Force
    }
}

$shell = New-Object -ComObject WScript.Shell
$startupDir = [Environment]::GetFolderPath('Startup')
$programsDir = [Environment]::GetFolderPath('Programs')
$startupShortcut = Join-Path $startupDir '大肥鱼 Codex 增强桌宠.lnk'
$manualShortcut = Join-Path $programsDir '大肥鱼 Codex 增强桌宠.lnk'
$userId = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$controllerDataArg = "--data-dir `"$dataDir`""
$residentAction = New-ScheduledTaskAction -Execute $pythonwExe -Argument "`"$controllerMain`" $controllerDataArg"
$manualAction = New-ScheduledTaskAction -Execute $pythonwExe -Argument "`"$controllerMain`" $controllerDataArg --enable"
$residentTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$residentSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$manualSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances Parallel
Register-ScheduledTask -TaskName $residentTaskName -Action $residentAction -Trigger $residentTrigger -Principal $principal -Settings $residentSettings -Description '大肥鱼 Codex 增强桌宠常驻控制器' -Force | Out-Null
Register-ScheduledTask -TaskName $manualTaskName -Action $manualAction -Principal $principal -Settings $manualSettings -Description '手动开启或显示大肥鱼 Codex 增强桌宠' -Force | Out-Null

# The old Startup-folder process could inherit the Codex AppContainer job when
# installed from Codex and be killed with the app. Task Scheduler owns the new
# process, so the tray survives while only the pet follows Codex lifecycle.
if (Test-Path -LiteralPath $startupShortcut) {
    Remove-Item -LiteralPath $startupShortcut -Force
}
function Set-ControllerShortcut([string]$Path) {
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = (Join-Path $env:WINDIR 'System32\schtasks.exe')
    $shortcut.Arguments = "/Run /TN `"$manualTaskName`""
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.Description = '大肥鱼 Codex 增强桌宠'
    $shortcut.Save()

    $saved = $shell.CreateShortcut($Path)
    if (-not $saved.TargetPath -or $saved.Arguments -ne "/Run /TN `"$manualTaskName`"") {
        throw "Failed to create controller shortcut: $Path"
    }
}
Set-ControllerShortcut $manualShortcut

if (-not $SkipLaunch) {
    Start-ScheduledTask -TaskName $manualTaskName
}

[pscustomobject]@{
    Installed = $true
    InstallRoot = $InstallRoot
    Hooks = $hooksPath
    ResidentTask = $residentTaskName
    ManualTask = $manualTaskName
    ManualShortcut = $manualShortcut
    RequiresHookTrust = $true
    PythonRoot = $installedPythonRoot
    SettingsReset = [bool]$ResetSettings
}
