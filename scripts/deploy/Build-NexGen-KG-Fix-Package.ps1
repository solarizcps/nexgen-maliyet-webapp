# Build V2 KG fix deploy ZIP (flat root layout, self-contained Deploy script).
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Ts = Get-Date -Format "yyyyMMdd_HHmmss"
$OutDir = Join-Path $env:USERPROFILE "Desktop\NexGen_KG_Save_Fix_3.0.3_V2_$Ts"
$ZipPath = "$OutDir.zip"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$files = @(
    "app.py", "config.py", "wsgi.py",
    "services\repository.py", "static\js\app.js"
)
foreach ($f in $files) {
    $dest = Join-Path $OutDir $f
    $destDir = Split-Path $dest -Parent
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
    Copy-Item (Join-Path $Root $f) $dest -Force
}

$pcPath = Join-Path $Root "scripts\production\NexGen-ProcessControl.ps1"
$deployPath = Join-Path $Root "scripts\deploy\Deploy-NexGen-KG-Fix.ps1"
$pcContent = Get-Content $pcPath -Raw
$deployContent = Get-Content $deployPath -Raw
if ($deployContent -match '(?s)(param\s*\([^)]*\)\s*)') { $paramBlock = $Matches[1] } else { $paramBlock = "" }
$deployBody = $deployContent -replace '(?s)^#requires[^\r\n]*\r?\n', ''
$deployBody = $deployBody -replace '(?s)^param\s*\([^)]*\)\s*', ''
$deployBody = $deployBody -replace '(?s)\$pcLoaded = \$false.*?if \(-not \$pcLoaded\) \{\s*throw.*?\}\r?\n', ''
$mergedDeploy = "#requires -Version 5.1`r`n$paramBlock# NexGen-ProcessControl inlined`r`n$pcContent`r`n$deployBody"
Set-Content -Path (Join-Path $OutDir "Deploy-NexGen-KG-Fix.ps1") -Value $mergedDeploy -Encoding UTF8
Copy-Item (Join-Path $Root "scripts\deploy\ROLLBACK.txt") (Join-Path $OutDir "ROLLBACK.txt") -Force

$commit = (git -C $Root rev-parse HEAD).Trim()
$fileEntries = @()
foreach ($f in $files) {
    $full = Join-Path $OutDir ($f -replace "\\", "/")
    $rel = $f -replace "\\", "/"
    $hash = (Get-FileHash (Join-Path $OutDir $f) -Algorithm SHA256).Hash.ToUpper()
    $fileEntries += [ordered]@{ path = $rel; sha256 = $hash }
}
$deployHash = (Get-FileHash (Join-Path $OutDir "Deploy-NexGen-KG-Fix.ps1") -Algorithm SHA256).Hash.ToUpper()
$manifest = [ordered]@{
    release_name = "NexGen KG Save/Calc Fix 3.0.3-kg-save V2"
    version = "3.0.3-kg-save"
    package_revision = "V2-task-race-fix"
    git_commit = $commit
    created_at = (Get-Date -Format "o")
    canonical_server_path = "C:\nexgen_maliyet"
    DB_INCLUDED = $false
    SECRET_INCLUDED = $false
    CPS_INCLUDED = $false
    files = $fileEntries
    deploy_script = [ordered]@{ path = "Deploy-NexGen-KG-Fix.ps1"; sha256 = $deployHash }
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutDir "manifest.json") -Encoding UTF8

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $OutDir "*") -DestinationPath $ZipPath -Force
Write-Host "PACKAGE_DIR=$OutDir"
Write-Host "PACKAGE_ZIP=$ZipPath"
Write-Host "GIT_COMMIT=$commit"
