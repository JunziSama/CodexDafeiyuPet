param(
    [string]$DataDir = ''
)

$ErrorActionPreference = 'SilentlyContinue'
$dataDir = if ($DataDir) {
    $DataDir
} elseif ($env:DAFEIYU_CONTROLLER_DATA_DIR) {
    $env:DAFEIYU_CONTROLLER_DATA_DIR
} else {
    Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\dafeiyu-companion-data'
}
$env:DAFEIYU_CONTROLLER_DATA_DIR = $dataDir
$configPath = Join-Path $dataDir 'controller.json'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { exit 0 }
try {
    $config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    $pythonExe = [string]$config.python_executable
} catch { exit 0 }
if (-not $pythonExe -or -not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) { exit 0 }
$hookPath = Join-Path $PSScriptRoot 'codex_event_hook.py'
& $pythonExe $hookPath
exit $LASTEXITCODE
