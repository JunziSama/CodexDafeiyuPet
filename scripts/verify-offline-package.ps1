[CmdletBinding()]
param(
    [string]$PackageRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [switch]$SkipProtocolSmoke
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path $PackageRoot).Path
$pythonRoot = Join-Path $root 'portable-python'
$pythonExe = Join-Path $pythonRoot 'python.exe'
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) { throw 'portable-python/python.exe is missing.' }
foreach ($forbidden in @('bridge-token', 'controller.log', 'hook-audit.json', 'controller.json')) {
    if (Get-ChildItem -LiteralPath $root -Recurse -File -Filter $forbidden -ErrorAction SilentlyContinue) {
        throw "Forbidden runtime file is present: $forbidden"
    }
}
$videos = @(Get-ChildItem -LiteralPath (Join-Path $root 'runtime\assets\characters\shenshen') -Recurse -File -Filter '*.webm')
if ($videos.Count -ne 91) { throw "Expected 91 WebM animations, found $($videos.Count)." }
$clickVideos = @(Get-ChildItem -LiteralPath (Join-Path $root 'runtime\assets\characters\shenshen\videos\click') -File -Filter '*.webm')
$randomVideos = @(Get-ChildItem -LiteralPath (Join-Path $root 'runtime\assets\characters\shenshen\videos\random') -File -Filter '*.webm')
if ($clickVideos.Count -ne 5) { throw "Expected 5 click animations, found $($clickVideos.Count)." }
if ($randomVideos.Count -ne 80) { throw "Expected 80 random animations, found $($randomVideos.Count)." }
$safePreferences = Get-Content -Raw -LiteralPath (Join-Path $root 'config\safe-preferences.json') | ConvertFrom-Json -AsHashtable
foreach ($forbiddenKey in @('rx','ry','chat','api_key','bridge_token','hook_last_event','hook_last_model_slug')) {
    if ($safePreferences.Contains($forbiddenKey)) { throw "Unsafe preference key is present: $forbiddenKey" }
}

$vendor = Join-Path $root 'runtime\vendor'
$runtime = Join-Path $root 'runtime'
$oldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $vendor + [IO.Path]::PathSeparator + $runtime
    & $pythonExe -c "import PySide6, PIL, imageio_ffmpeg; print('portable-imports-ok')"
    if ($LASTEXITCODE -ne 0) { throw 'Portable Python dependency import failed.' }
    if (-not $SkipProtocolSmoke) {
        foreach ($mode in @('current_then_farewell','farewell_only','current_only','bubble_sync')) {
            & $pythonExe (Join-Path $root 'scripts\smoke-farewell.py') --package-root $root --mode $mode --timeout 35
            if ($LASTEXITCODE -ne 0) { throw "Offline farewell protocol smoke failed: $mode" }
        }
    }
} finally {
    $env:PYTHONPATH = $oldPythonPath
}

$manifestPath = Join-Path $root 'PACKAGE-MANIFEST.sha256'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'PACKAGE-MANIFEST.sha256 is missing.' }
foreach ($line in Get-Content -LiteralPath $manifestPath) {
    if (-not $line.Trim()) { continue }
    $parts = $line -split '  ', 2
    $target = Join-Path $root ($parts[1] -replace '/', [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Manifest file missing: $($parts[1])" }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash -ne $parts[0]) {
        throw "Manifest hash mismatch: $($parts[1])"
    }
}
[pscustomobject]@{
    Valid = $true
    Platform = 'win-x64'
    Python = (& $pythonExe --version 2>&1 | Out-String).Trim()
    Animations = $videos.Count
    ClickAnimations = $clickVideos.Count
    RandomAnimations = $randomVideos.Count
    PackageRoot = $root
}
