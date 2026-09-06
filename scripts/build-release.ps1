[CmdletBinding()]
param(
    [string]$Version = '1.0.0',
    [string]$OutputRoot = '',
    [string]$PythonSourceRoot = '',
    [string]$VendorSourceRoot = ''
)

$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $OutputRoot) { $OutputRoot = Join-Path $sourceRoot "deliverables\v$Version" }
$outputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (-not $PythonSourceRoot) {
    $PythonSourceRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes\codex-primary-runtime\dependencies\python'
}
if (-not $VendorSourceRoot) { $VendorSourceRoot = Join-Path $sourceRoot 'runtime\vendor' }

foreach ($required in @(
    (Join-Path $PythonSourceRoot 'python.exe'),
    (Join-Path $VendorSourceRoot 'PySide6'),
    (Join-Path $sourceRoot 'ASSET_LICENSE.md')
)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required release input is missing: $required" }
}

function Assert-ChildPath([string]$Path, [string]$Parent) {
    $child = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetFullPath($Parent).TrimEnd([IO.Path]::DirectorySeparatorChar)
    if (-not $child.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes intended root: $child"
    }
}

function Remove-TreeSafe([string]$Path, [string]$Parent) {
    Assert-ChildPath $Path $Parent
    if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Recurse -Force }
}

function Remove-Caches([string]$Root) {
    Get-ChildItem -LiteralPath $Root -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @('__pycache__', '.pytest_cache', '.cache') } |
        Sort-Object FullName -Descending |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    Get-ChildItem -LiteralPath $Root -Recurse -File -Force -Include '*.pyc','*.pyo' -ErrorAction SilentlyContinue |
        Remove-Item -Force
}

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
$stageRoot = Join-Path $outputRoot '_staging'
Remove-TreeSafe $stageRoot $outputRoot
$packageRoot = Join-Path $stageRoot 'CodexDafeiyuPet-Offline-Win-x64'
New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null

$releaseNames = @(
    'controller','hooks','runtime','config','docs','test','src','lib',
    'README-CODEX.md','README.md','README-PLUGIN.md','DEVELOPMENT.md','BUBBLE_SPEC.md','ANIMATION_SCHEDULE.md',
    'COLOR_CALIBRATION.md','INSTALL.md','LICENSE','ASSET_LICENSE.md','CREDITS.md','requirements.txt',
    'package.json','cordis.patch.yml'
)
foreach ($name in $releaseNames) {
    $source = Join-Path $sourceRoot $name
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $packageRoot $name) -Recurse -Force
    }
}
New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot 'scripts') | Out-Null
foreach ($name in @('install-codex.ps1','uninstall-codex.ps1','verify-offline-package.ps1','smoke-farewell.py')) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot "scripts\$name") -Destination (Join-Path $packageRoot "scripts\$name") -Force
}
$codexReadme = Join-Path $packageRoot 'README-CODEX.md'
if (Test-Path -LiteralPath $codexReadme) {
    $pluginReadme = Join-Path $packageRoot 'README.md'
    if (Test-Path -LiteralPath $pluginReadme) {
        Move-Item -LiteralPath $pluginReadme -Destination (Join-Path $packageRoot 'README-PLUGIN.md') -Force
    }
    Move-Item -LiteralPath $codexReadme -Destination (Join-Path $packageRoot 'README.md') -Force
}

$vendorTarget = Join-Path $packageRoot 'runtime\vendor'
if (Test-Path -LiteralPath $vendorTarget) { Remove-TreeSafe $vendorTarget $packageRoot }
Copy-Item -LiteralPath $VendorSourceRoot -Destination $vendorTarget -Recurse -Force

$portable = Join-Path $packageRoot 'portable-python'
New-Item -ItemType Directory -Force -Path $portable | Out-Null
foreach ($name in @('python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt')) {
    Copy-Item -LiteralPath (Join-Path $PythonSourceRoot $name) -Destination $portable -Force
}
Copy-Item -LiteralPath (Join-Path $PythonSourceRoot 'DLLs') -Destination (Join-Path $portable 'DLLs') -Recurse -Force
Copy-Item -LiteralPath (Join-Path $PythonSourceRoot 'Lib') -Destination (Join-Path $portable 'Lib') -Recurse -Force
Remove-TreeSafe (Join-Path $portable 'Lib\site-packages') $portable
Remove-Caches $packageRoot

@'
# 第三方运行库

本包包含 Python 3.12、PySide6/Shiboken6、Pillow 和 imageio-ffmpeg。Python 许可证位于
`portable-python/LICENSE.txt`；Python 包许可证保留在 `runtime/vendor` 下对应的
`*.dist-info/licenses` 或许可证文件中。角色与动画素材许可见 `ASSET_LICENSE.md`。
'@ | Set-Content -LiteralPath (Join-Path $packageRoot 'THIRD-PARTY-NOTICES.md') -Encoding utf8

foreach ($forbidden in @('bridge-token','controller.log','hook-audit.json','controller.json')) {
    if (Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Filter $forbidden -ErrorAction SilentlyContinue) {
        throw "Forbidden runtime state entered package: $forbidden"
    }
}
$videos = @(Get-ChildItem -LiteralPath (Join-Path $packageRoot 'runtime\assets\characters\shenshen') -Recurse -File -Filter '*.webm')
if ($videos.Count -ne 91) { throw "Expected 91 WebM animations, found $($videos.Count)." }

$manifest = Join-Path $packageRoot 'PACKAGE-MANIFEST.sha256'
$manifestLines = Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    $relative = [IO.Path]::GetRelativePath($packageRoot, $_.FullName).Replace('\', '/')
    "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash, $relative
}
[IO.File]::WriteAllLines($manifest, $manifestLines, [Text.UTF8Encoding]::new($false))

$zipName = "CodexDafeiyuPet-Offline-Win-x64-v$Version.zip"
$zipPath = Join-Path $outputRoot $zipName
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($packageRoot, $zipPath, [IO.Compression.CompressionLevel]::Optimal, $false, [Text.Encoding]::UTF8)
$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash
[IO.File]::WriteAllLines((Join-Path $outputRoot 'SHA256SUMS.txt'), @("$zipHash  $zipName"), [Text.UTF8Encoding]::new($false))
Remove-TreeSafe $stageRoot $outputRoot

[pscustomobject]@{
    Version = $Version
    Zip = $zipPath
    SHA256 = $zipHash
    SizeMiB = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 2)
    Animations = $videos.Count
}
