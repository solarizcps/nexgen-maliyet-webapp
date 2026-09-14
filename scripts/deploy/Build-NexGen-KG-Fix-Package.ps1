# Build V3 KG fix deploy ZIP (flat root, 7 production files + 3 helpers).
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Ts = Get-Date -Format "yyyyMMdd_HHmmss"
$OutDir = Join-Path $env:USERPROFILE "Desktop\NexGen_KG_Save_Fix_3.0.3_V3_$Ts"
$ZipPath = "$OutDir.zip"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$files = @(
    "app.py",
    "config.py",
    "wsgi.py",
    "services\repository.py",
    "static\js\app.js",
    "scripts\production\NexGen-ProcessControl.ps1",
    "scripts\production\Stop-NexGen-2333.ps1"
)
foreach ($f in $files) {
    $dest = Join-Path $OutDir $f
    $destDir = Split-Path $dest -Parent
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
    Copy-Item (Join-Path $Root $f) $dest -Force
}

Copy-Item (Join-Path $Root "scripts\deploy\Deploy-NexGen-KG-Fix.ps1") (Join-Path $OutDir "Deploy-NexGen-KG-Fix.ps1") -Force
Copy-Item (Join-Path $Root "scripts\deploy\ROLLBACK.txt") (Join-Path $OutDir "ROLLBACK.txt") -Force

$commit = (git -C $Root rev-parse HEAD).Trim()
$fileEntries = @()
foreach ($f in $files) {
    $rel = $f -replace "\\", "/"
    $hash = (Get-FileHash (Join-Path $OutDir $f) -Algorithm SHA256).Hash.ToUpper()
    $fileEntries += [ordered]@{ path = $rel; sha256 = $hash }
}
$deployHash = (Get-FileHash (Join-Path $OutDir "Deploy-NexGen-KG-Fix.ps1") -Algorithm SHA256).Hash.ToUpper()
$manifest = [ordered]@{
    release_name = "NexGen KG Save/Calc Fix 3.0.3-kg-save V3"
    version = "3.0.3-kg-save"
    package_revision = "V3-complete-task-race-fix"
    git_commit = $commit
    created_at = (Get-Date -Format "o")
    canonical_server_path = "C:\nexgen_maliyet"
    production_files_count = 7
    deploy_helper_files_count = 3
    total_files_count = 10
    DB_INCLUDED = $false
    SECRET_INCLUDED = $false
    CPS_INCLUDED = $false
    files = $fileEntries
    deploy_script = [ordered]@{ path = "Deploy-NexGen-KG-Fix.ps1"; sha256 = $deployHash }
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutDir "manifest.json") -Encoding UTF8

$packageFileCount = (Get-ChildItem $OutDir -Recurse -File).Count
if ($packageFileCount -ne 10) {
    throw "Expected 10 package files, found $packageFileCount"
}

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $OutDir "*") -DestinationPath $ZipPath -Force
Write-Host "PACKAGE_DIR=$OutDir"
Write-Host "PACKAGE_ZIP=$ZipPath"
Write-Host "GIT_COMMIT=$commit"
Write-Host "PRODUCTION_FILES_COUNT=7"
Write-Host "TOTAL_PACKAGE_FILES=10"
