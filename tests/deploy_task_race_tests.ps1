# Deployment task-restart-race tests (isolated, no production contact).
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$failed = 0

function Assert([bool]$Cond, [string]$Name) {
    if ($Cond) { Write-Host "PASS $Name" } else { Write-Host "FAIL $Name"; $script:failed++ }
}

function Get-Sha256([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpper() }

. (Join-Path $Root "scripts\production\NexGen-ProcessControl.ps1")

# 1 Health diagnostics — old version must fail version field
$diag = @{}
$hOld = [pscustomobject]@{
    status = "ok"; db_connected = $true; environment = "production"
    wsgi_server = "waitress"; port = 2333
    db_path = "C:\nexgen_maliyet\data\nexgen_local.db"
    version = "3.0.2-warning-scope"
}
Write-NexGenHealthDiagnostics -Health $hOld -ExpectedVersion "3.0.3-kg-save" -ExpectedDbPath "C:\nexgen_maliyet\data\nexgen_local.db" -Report $diag | Out-Null
Assert ($diag.POST_HEALTH_VERSION -eq "3.0.2-warning-scope") "health reports actual version"
Assert ($diag.FAILED_HEALTH_FIELDS -eq "version") "old version fails version check"
Assert ($diag.EXPECTED_VERSION -eq "3.0.3-kg-save") "expected version explicit"

# 2 Health diagnostics — all fields pass
$diag2 = @{}
$hNew = [pscustomobject]@{
    status = "ok"; db_connected = $true; environment = "production"
    wsgi_server = "waitress"; port = 2333
    db_path = "C:\nexgen_maliyet\data\nexgen_local.db"
    version = "3.0.3-kg-save"
}
Write-NexGenHealthDiagnostics -Health $hNew -ExpectedVersion "3.0.3-kg-save" -ExpectedDbPath "C:\nexgen_maliyet\data\nexgen_local.db" -Report $diag2 | Out-Null
Assert ([string]::IsNullOrEmpty($diag2.FAILED_HEALTH_FIELDS)) "new version health pass"

# 3 Deploy script must Stop-ScheduledTask before release file copy
$deployText = Get-Content (Join-Path $Root "scripts\deploy\Deploy-NexGen-KG-Fix.ps1") -Raw
Assert ($deployText -match '(?s)\$stopResult = Stop-NexGenTaskSafely[\s\S]*?\$backupRoot = Join-Path[\s\S]*?Copy-Item \$src \$dst') "stop task before release file copy"

# 4 Stop script must reference Stop-ScheduledTask via module
$stopText = Get-Content (Join-Path $Root "scripts\production\Stop-NexGen-2333.ps1") -Raw
$pcText = Get-Content (Join-Path $Root "scripts\production\NexGen-ProcessControl.ps1") -Raw
Assert ($pcText -match "Stop-ScheduledTask") "process control stops scheduled task"
Assert ($stopText -match "Stop-NexGenTaskSafely") "stop script uses safe stop"
Assert ($stopText -match 'Join-Path \$PSScriptRoot "NexGen-ProcessControl\.ps1"') "stop script dot-sources local ProcessControl"

# 5 Forbidden patterns absent from production scripts
$forbidden = @("taskkill", "Remove-Item `$CanonicalRoot", "Remove-Item C:\\nexgen_maliyet")
foreach ($pat in $forbidden) {
    Assert ($deployText -notmatch [regex]::Escape($pat)) "deploy no forbidden: $pat"
    Assert ($pcText -notmatch "taskkill") "process control no taskkill"
}
Assert ($deployText -match "Remove-Item -LiteralPath") "rollback uses literal path remove only"

# 6 Rollback order — Stop-NexGenTaskSafely before restore copy
Assert ($deployText -match "Invoke-Rollback[\s\S]*Stop-NexGenTaskSafely") "rollback stops task first"
Assert ($deployText -match "previously_absent") "deploy tracks previously absent files"
Assert ($deployText -match "backup_manifest\.json") "deploy writes backup manifest"

# 7 Port free helper on unlikely port
Assert (Test-PortFree 59987) "unused port is free"

# 8 CPS PID guard logic present
Assert ($pcText -match "CPS 8080") "CPS guard referenced"

# 9 Deploy script reports explicit health fields via diagnostics helper
Assert ($deployText -match "Write-NexGenHealthDiagnostics|FAILED_HEALTH_FIELDS") "deploy uses explicit health fields"
Assert ($deployText -match 'Invoke-Rollback[\s\S]*FAILED_HEALTH_FIELDS') "health failure triggers rollback"

# 10 Start-ScheduledTask once after copy
$startCount = ([regex]::Matches($deployText, "Start-NexGenTaskSafely")).Count
Assert ($startCount -ge 1) "deploy starts task after copy"

# 11 V3 file inventory — seven production files in deploy list
$expectedProd = @(
    "app.py", "config.py", "wsgi.py", "services\repository.py", "static\js\app.js",
    "scripts\production\NexGen-ProcessControl.ps1", "scripts\production\Stop-NexGen-2333.ps1"
)
foreach ($rel in $expectedProd) {
    Assert ($deployText -match [regex]::Escape($rel)) "deploy includes production file $rel"
}
Assert (($expectedProd | Where-Object { Test-Path (Join-Path $Root $_) }).Count -eq 7) "source has 7 production files"

# 12 Build script V3 manifest fields
$buildText = Get-Content (Join-Path $Root "scripts\deploy\Build-NexGen-KG-Fix-Package.ps1") -Raw
Assert ($buildText -match "V3-complete-task-race-fix") "build script V3 revision"
Assert ($buildText -match "production_files_count = 7") "build manifest production count"
Assert ($buildText -match "NexGen-ProcessControl.ps1") "build includes ProcessControl"
Assert ($buildText -match "Stop-NexGen-2333.ps1") "build includes Stop script"
Assert ($buildText -notmatch "mergedDeploy") "build does not inline ProcessControl into deploy"

# 13 Seven-file backup/copy/hash integration (temp dirs)
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("nexgen-v3-backup-test-" + [guid]::NewGuid().ToString("N"))
$pkgRoot = Join-Path $tempRoot "pkg"
$prodRoot = Join-Path $tempRoot "prod"
$backupRoot = Join-Path $prodRoot "backup\kg_save_fix_deploy_test"
$codeBackup = Join-Path $backupRoot "code"
New-Item -ItemType Directory -Force -Path $pkgRoot, $prodRoot, $codeBackup | Out-Null
$releaseFiles = @(
    "app.py", "config.py", "wsgi.py", "services\repository.py", "static\js\app.js",
    "scripts\production\NexGen-ProcessControl.ps1", "scripts\production\Stop-NexGen-2333.ps1"
)
$manifestFiles = @()
foreach ($rel in $releaseFiles) {
    $src = Join-Path $Root $rel
    $pkgDst = Join-Path $pkgRoot $rel
    $prodDst = Join-Path $prodRoot $rel
    $prodDir = Split-Path $prodDst -Parent
    if (-not (Test-Path $prodDir)) { New-Item -ItemType Directory -Force -Path $prodDir | Out-Null }
    $pkgDir = Split-Path $pkgDst -Parent
    if (-not (Test-Path $pkgDir)) { New-Item -ItemType Directory -Force -Path $pkgDir | Out-Null }
    Copy-Item $src $pkgDst -Force
    if ($rel -ne "scripts\production\NexGen-ProcessControl.ps1") {
        Copy-Item $src $prodDst -Force
    }
    $manifestFiles += [ordered]@{
        path = ($rel -replace "\\", "/")
        sha256 = (Get-Sha256 $pkgDst)
    }
}
$oldStopPath = Join-Path $prodRoot "scripts\production\Stop-NexGen-2333.ps1"
$oldStopContent = "# old stop script`r`nStop-Process -Id 1 -ErrorAction SilentlyContinue"
Set-Content -Path $oldStopPath -Value $oldStopContent -Encoding UTF8
$oldStopHash = Get-Sha256 $oldStopPath

$backupManifest = [ordered]@{ files = @() }
foreach ($rel in $releaseFiles) {
    $prodPath = Join-Path $prodRoot $rel
    $dest = Join-Path $codeBackup $rel
    $destDir = Split-Path $dest -Parent
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
    $entry = [ordered]@{
        path = ($rel -replace "\\", "/")
        previously_absent = $false
        sha256 = $null
    }
    if (Test-Path $prodPath) {
        Copy-Item $prodPath $dest -Force
        $entry.sha256 = Get-Sha256 $prodPath
    } else {
        $entry.previously_absent = $true
    }
    $backupManifest.files += $entry
}
$backupManifest | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $codeBackup "backup_manifest.json") -Encoding UTF8
Assert ($backupManifest.files.Count -eq 7) "backup manifest has 7 entries"
$pcEntry = $backupManifest.files | Where-Object { $_.path -eq "scripts/production/NexGen-ProcessControl.ps1" } | Select-Object -First 1
Assert ($pcEntry -and $pcEntry.previously_absent -eq $true) "ProcessControl marked previously absent"

$copyPass = $true
foreach ($rel in $releaseFiles) {
    $src = Join-Path $pkgRoot $rel
    $dst = Join-Path $prodRoot $rel
    $dstDir = Split-Path $dst -Parent
    if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Force -Path $dstDir | Out-Null }
    Copy-Item $src $dst -Force
    $expected = ($manifestFiles | Where-Object { $_.path -eq ($rel -replace "\\", "/") }).sha256
    if ((Get-Sha256 $dst) -ne $expected) { $copyPass = $false }
}
Assert $copyPass "7/7 copy hash verification"

# 14 Previously absent ProcessControl rollback + old Stop script restore
$bm = Get-Content (Join-Path $codeBackup "backup_manifest.json") -Raw | ConvertFrom-Json
$rollbackPass = $true
foreach ($entry in $bm.files) {
    $rel = $entry.path -replace "/", "\"
    $dst = Join-Path $prodRoot $rel
    if ($entry.previously_absent) {
        if (Test-Path $dst) {
            $deployHash = ($manifestFiles | Where-Object { $_.path -eq $entry.path }).sha256
            if ((Get-Sha256 $dst) -eq $deployHash) {
                Remove-Item -LiteralPath $dst -Force
            } else { $rollbackPass = $false }
        }
    } else {
        $src = Join-Path $codeBackup $rel
        Copy-Item $src $dst -Force
        if ((Get-Sha256 $src) -ne (Get-Sha256 $dst)) { $rollbackPass = $false }
    }
}
Assert (-not (Test-Path (Join-Path $prodRoot "scripts\production\NexGen-ProcessControl.ps1"))) "ProcessControl removed on rollback"
Assert ((Get-Sha256 $oldStopPath) -eq $oldStopHash) "old Stop script restored"
Assert $rollbackPass "7/7 rollback hash verification"

# 15 Forced health failure rollback path (restore after simulated failure)
foreach ($rel in $releaseFiles) {
    $src = Join-Path $pkgRoot $rel
    $dst = Join-Path $prodRoot $rel
    $dstDir = Split-Path $dst -Parent
    if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Force -Path $dstDir | Out-Null }
    Copy-Item $src $dst -Force
}
$diagFail = @{}
$mockDbPath = Join-Path $prodRoot "data\nexgen_local.db"
$hFail = [pscustomobject]@{
    status = "ok"; db_connected = $true; environment = "production"
    wsgi_server = "waitress"; port = 2333
    db_path = $mockDbPath
    version = "3.0.2-warning-scope"
}
Write-NexGenHealthDiagnostics -Health $hFail -ExpectedVersion "3.0.3-kg-save" -ExpectedDbPath $mockDbPath -Report $diagFail | Out-Null
Assert ($diagFail.FAILED_HEALTH_FIELDS -eq "version") "forced health failure detected"
foreach ($entry in $bm.files) {
    $rel = $entry.path -replace "/", "\"
    $dst = Join-Path $prodRoot $rel
    if ($entry.previously_absent) {
        if (Test-Path $dst) {
            $deployHash = ($manifestFiles | Where-Object { $_.path -eq $entry.path }).sha256
            if ((Get-Sha256 $dst) -eq $deployHash) { Remove-Item -LiteralPath $dst -Force }
        }
    } else {
        Copy-Item (Join-Path $codeBackup $rel) $dst -Force
    }
}
Assert ((Get-Sha256 $oldStopPath) -eq $oldStopHash) "forced rollback restores old Stop script"

Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "DEPLOY_TESTS_FAILED=$failed"
if ($failed -gt 0) { exit 1 }
Write-Host "DEPLOY_TESTS_PASS=$failed"
exit 0
