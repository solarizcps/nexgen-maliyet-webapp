#requires -Version 5.1
param(
    [switch]$ValidateOnly,
    [string]$TestProductionRoot = "",
    [switch]$SkipScheduledTask
)

$ErrorActionPreference = "Stop"
$ReleaseRoot = $PSScriptRoot
$ManifestPath = Join-Path $ReleaseRoot "manifest.json"
$ExpectedVersion = "3.0.3-kg-save"
$TaskName = "NexGen-Maliyet-2333"
$Port = 2333
$DeployTs = Get-Date -Format "yyyyMMdd_HHmmss"
$CanonicalRoot = if ($TestProductionRoot) { $TestProductionRoot } else { "C:\nexgen_maliyet" }

$pcLoaded = $false
foreach ($candidate in @(
    (Join-Path $ReleaseRoot "NexGen-ProcessControl.ps1"),
    (Join-Path $CanonicalRoot "scripts\production\NexGen-ProcessControl.ps1"),
    (Join-Path (Split-Path $PSScriptRoot -Parent) "production\NexGen-ProcessControl.ps1")
)) {
    if (Test-Path $candidate) {
        . $candidate
        $pcLoaded = $true
        break
    }
}
if (-not $pcLoaded) {
    throw "NexGen-ProcessControl.ps1 not found"
}

$Report = [ordered]@{
    phase = "NEXGEN_KG_SAVE_FIX_DEPLOY"
    hostname = $env:COMPUTERNAME
    timestamp = (Get-Date -Format "o")
    release_root = $ReleaseRoot
    production_root = $CanonicalRoot
}

function Write-Report([string]$Key, $Value) { $Report[$Key] = $Value }
function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Get-Sha256([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpper() }

function Get-Cps8080Snapshot {
    $snap = [ordered]@{ pid = (Get-Cps8080Pid) }
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8080/" -UseBasicParsing -TimeoutSec 3 -MaximumRedirection 0
        $snap.http_status = [int]$r.StatusCode
    } catch {
        if ($_.Exception.Response) { $snap.http_status = [int]$_.Exception.Response.StatusCode } else { $snap.http_status = $null }
    }
    return $snap
}

function Invoke-DbPython([string]$PyCode) {
    $python = Join-Path $CanonicalRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
    $tmp = [IO.Path]::GetTempFileName() + ".py"
    Set-Content -Path $tmp -Value $PyCode -Encoding UTF8
    try {
        $out = & $python $tmp 2>&1
        if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) { throw "Python failed: $out" }
        return ($out | Out-String).Trim()
    } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
}

function Get-DbCounts([string]$DbPath) {
    $code = @"
import json, sqlite3
db = r'$DbPath'
c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
cur = c.cursor()
out = {'integrity': cur.execute('PRAGMA integrity_check').fetchone()[0]}
for t in ['users','materials','companies','formulas','formula_lines','expenses','weekly_price_reviews','material_price_history','audit_log']:
    out[t] = cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
row = cur.execute("SELECT fl.quantity_kg FROM formula_lines fl JOIN materials m ON m.id=fl.material_id JOIN formulas f ON f.id=fl.formula_id WHERE f.id='neo-taban' AND m.code='PROFOR'").fetchone()
out['neo_profor_kg'] = row[0] if row else None
c.close()
print(json.dumps(out))
"@
    return (Invoke-DbPython $code | ConvertFrom-Json)
}

function Invoke-SqliteOnlineBackup([string]$SourceDb, [string]$DestDb) {
    $script = Join-Path $CanonicalRoot "scripts\sqlite_online_backup.py"
    $python = Join-Path $CanonicalRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
    if (Test-Path $script) {
        return (& $python $script $SourceDb $DestDb | ConvertFrom-Json)
    }
    $code = @"
import json, sqlite3, hashlib
src, dst = r'$SourceDb', r'$DestDb'
s = sqlite3.connect(src); d = sqlite3.connect(dst)
s.backup(d); d.close(); s.close()
h = hashlib.sha256()
with open(dst,'rb') as f:
    for chunk in iter(lambda: f.read(1048576), b''): h.update(chunk)
print(json.dumps({'sha256': h.hexdigest().upper(), 'dest': dst}))
"@
    return (Invoke-DbPython $code | ConvertFrom-Json)
}

function Test-PackageIntegrity {
    if (-not (Test-Path $ManifestPath)) { throw "manifest.json missing" }
    $manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
    if ($manifest.version -ne $ExpectedVersion) { throw "Unexpected version $($manifest.version)" }
    foreach ($item in $manifest.files) {
        $rel = $item.path -replace "/", "\"
        $full = Join-Path $ReleaseRoot $rel
        if (-not (Test-Path $full)) { throw "Missing package file: $($item.path)" }
        if ((Get-Sha256 $full) -ne $item.sha256.ToUpper()) {
            throw "Hash mismatch $($item.path)"
        }
    }
    $forbidden = Get-ChildItem $ReleaseRoot -Recurse -File | Where-Object {
        $_.Extension -match '\.(db|secret|log|pid|lock)$' -or $_.Name -match 'mock_data|nexgen_local|\.nexgen_secret'
    }
    if ($forbidden) { throw "Forbidden files in package" }
    return $manifest
}

function Get-HealthSnapshot([string]$Label) {
    $h = Get-NexGenHealthJson "http://127.0.0.1:$Port"
    $listenerPid = Get-PortListenerPid $Port
    $taskState = $null
    if (-not $SkipScheduledTask) {
        $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($t) { $taskState = $t.State.ToString() }
    }
    return [ordered]@{
        label = $Label
        timestamp = (Get-Date -Format "o")
        pid = $listenerPid
        task_state = $taskState
        version = if ($h) { $h.version } else { $null }
        status = if ($h) { $h.status } else { $null }
    }
}

function Invoke-Rollback([string]$BackupRoot, [string]$Reason, [string]$ExpectedRollbackVersion) {
    Write-Report "rollback_reason" $Reason
    Write-Host "ROLLBACK: $Reason"
    try {
        Stop-NexGenTaskSafely -ProductionRoot $CanonicalRoot -TaskName $TaskName -Port $Port -SkipScheduledTask:$SkipScheduledTask | Out-Null
    } catch {
        Write-Report "rollback_stop_error" $_.Exception.Message
    }
    $codeBackup = Join-Path $BackupRoot "code"
    $releaseFiles = @("app.py", "config.py", "wsgi.py", "services\repository.py", "static\js\app.js")
    foreach ($rel in $releaseFiles) {
        $src = Join-Path $codeBackup $rel
        $dst = Join-Path $CanonicalRoot $rel
        if (-not (Test-Path $src)) { continue }
        $dstDir = Split-Path $dst -Parent
        if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Force -Path $dstDir | Out-Null }
        Copy-Item $src $dst -Force
        $bakHash = Get-Sha256 $src
        $prodHash = Get-Sha256 $dst
        if ($bakHash -ne $prodHash) { throw "Rollback hash mismatch for $rel" }
    }
    Start-NexGenTaskSafely -TaskName $TaskName -SkipScheduledTask:$SkipScheduledTask | Out-Null
    $deadline = (Get-Date).AddSeconds(30)
    $rbHealth = $null
    while ((Get-Date) -lt $deadline) {
        $rbHealth = Get-NexGenHealthJson "http://127.0.0.1:$Port"
        if ($rbHealth -and $rbHealth.status -eq "ok") { break }
        Start-Sleep -Seconds 2
    }
    $snap = Get-HealthSnapshot "rollback"
    Write-Report "rollback_health_snapshot" $snap
    if ($ExpectedRollbackVersion -and $rbHealth -and $rbHealth.version -ne $ExpectedRollbackVersion) {
        Write-Report "ROLLBACK_RESULT" "FAIL version=$($rbHealth.version)"
        exit 1
    }
    $cps = Get-Cps8080Snapshot
    if ($cps.http_status -ne 200 -and $null -ne $cps.http_status) {
        Write-Report "ROLLBACK_CPS_HTTP" $cps.http_status
    }
    Write-Report "ROLLBACK_RESULT" "PASS"
    exit 1
}

$ReleaseFiles = @(
    @{ Rel = "app.py"; Prod = "app.py" },
    @{ Rel = "config.py"; Prod = "config.py" },
    @{ Rel = "wsgi.py"; Prod = "wsgi.py" },
    @{ Rel = "services\repository.py"; Prod = "services\repository.py" },
    @{ Rel = "static\js\app.js"; Prod = "static\js\app.js" }
)

try {
    $manifest = Test-PackageIntegrity
    $ExpectedCommit = $manifest.git_commit
    Write-Report "manifest_git_commit" $ExpectedCommit

    if ($ValidateOnly) {
        Write-Host "PACKAGE_VALIDATE_PASS"
        Write-Report "VALIDATE_ONLY" "PASS"
        $Report | ConvertTo-Json -Depth 6
        exit 0
    }

    if (-not $TestProductionRoot -and -not (Test-IsAdmin)) {
        Write-Error "Administrator privileges required."
        exit 1
    }

    $dbPath = Join-Path $CanonicalRoot "data\nexgen_local.db"
    $secretPath = Join-Path $CanonicalRoot "data\.nexgen_secret"
    if (-not (Test-Path $CanonicalRoot)) { throw "Production root missing" }
    if (-not (Test-Path $dbPath)) { throw "Missing DB" }
    if (-not (Test-Path $secretPath)) { throw "Missing secret file" }

    $preCounts = Get-DbCounts $dbPath
    if ($preCounts.integrity -ne "ok") { throw "DB integrity failed" }
    Write-Report "pre_db_counts" $preCounts

    $preHealth = Get-NexGenHealthJson "http://127.0.0.1:$Port"
    $prePid = Get-PortListenerPid $Port
    $preVersion = if ($preHealth) { $preHealth.version } else { $null }
    Write-Report "pre_health_snapshot" (Get-HealthSnapshot "pre_deploy")
    Write-Report "pre_nexgen_pid" $prePid
    Write-Report "pre_version" $preVersion

    $cpsBefore = Get-Cps8080Snapshot
    Write-Report "cps_8080_before" $cpsBefore

    if (-not $SkipScheduledTask) {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $task) { throw "Scheduled Task missing: $TaskName" }
        Write-Report "task_state_before" $task.State.ToString()
    }

    if ($TestProductionRoot -and $SkipScheduledTask) {
        $stopResult = [ordered]@{ task_stopped = $false; task_ready = $true; port_free = $true; mock_skip = $true }
        Write-Report "stop_result" $stopResult
    } else {
        $stopResult = Stop-NexGenTaskSafely -ProductionRoot $CanonicalRoot -TaskName $TaskName -Port $Port -SkipScheduledTask:$SkipScheduledTask
        Write-Report "stop_result" $stopResult
        if (-not $stopResult.port_free) {
            throw "Port $Port not free after stop - aborting before file copy"
        }
    }

    $backupRoot = Join-Path $CanonicalRoot "backup\kg_save_fix_deploy_$DeployTs"
    $codeBackup = Join-Path $backupRoot "code"
    $dataBackup = Join-Path $backupRoot "data"
    New-Item -ItemType Directory -Force -Path $codeBackup, $dataBackup | Out-Null

    foreach ($f in $ReleaseFiles) {
        $dest = Join-Path $codeBackup $f.Prod
        $destDir = Split-Path $dest -Parent
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
        Copy-Item (Join-Path $CanonicalRoot $f.Prod) $dest -Force
    }
    Copy-Item $secretPath (Join-Path $dataBackup ".nexgen_secret") -Force
    $destDb = Join-Path $dataBackup "nexgen_local.db"
    $bakMeta = Invoke-SqliteOnlineBackup $dbPath $destDb
    Write-Report "db_backup_meta" $bakMeta
    if ((Get-DbCounts $destDb).integrity -ne "ok") { throw "Backup DB integrity failed" }

    foreach ($f in $ReleaseFiles) {
        $src = Join-Path $ReleaseRoot ($f.Rel -replace "/", "\")
        $dst = Join-Path $CanonicalRoot $f.Prod
        $dstDir = Split-Path $dst -Parent
        if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Force -Path $dstDir | Out-Null }
        Copy-Item $src $dst -Force
        $expected = ($manifest.files | Where-Object { ($_.path -replace "/", "\") -eq $f.Rel }).sha256.ToUpper()
        if ((Get-Sha256 $dst) -ne $expected) {
            Invoke-Rollback $backupRoot "Post-copy hash mismatch $($f.Prod)" $preVersion
        }
    }

    $mockDryRun = ($TestProductionRoot -and $SkipScheduledTask)
    if (-not $mockDryRun) {
        Start-NexGenTaskSafely -TaskName $TaskName -SkipScheduledTask:$SkipScheduledTask | Out-Null
        $deadline = (Get-Date).AddSeconds(30)
        $postHealth = $null
        while ((Get-Date) -lt $deadline) {
            $postHealth = Get-NexGenHealthJson "http://127.0.0.1:$Port"
            if ($postHealth -and $postHealth.status -eq "ok") { break }
            Start-Sleep -Seconds 2
        }

        $postPid = Get-PortListenerPid $Port
        Write-Report "post_health_snapshot" (Get-HealthSnapshot "post_deploy")
        Write-Report "post_nexgen_pid" $postPid

        if (-not $postHealth) {
            Invoke-Rollback $backupRoot "Health timeout after start" $preVersion
        }

        $diag = @{}
        Write-NexGenHealthDiagnostics -Health $postHealth -ExpectedVersion $ExpectedVersion -ExpectedDbPath $dbPath -Report $diag | Out-Null
        foreach ($k in $diag.Keys) { Write-Report $k $diag[$k] }

        if ($diag["FAILED_HEALTH_FIELDS"]) {
            Invoke-Rollback $backupRoot "Post-deploy health failed: $($diag['FAILED_HEALTH_FIELDS'])" $preVersion
        }

        if ($prePid -and $postPid -and ($prePid -eq $postPid) -and -not $SkipScheduledTask) {
            Invoke-Rollback $backupRoot "Post-deploy PID unchanged ($postPid) - possible task restart race" $preVersion
        }

        if (-not $SkipScheduledTask) {
            $taskAfter = Get-ScheduledTask -TaskName $TaskName
            Write-Report "task_state_after" $taskAfter.State.ToString()
            if ($taskAfter.State -ne "Running") {
                Invoke-Rollback $backupRoot "Task not Running after deploy" $preVersion
            }
        }

        try {
            Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/data" -UseBasicParsing -TimeoutSec 5 | Out-Null
            Invoke-Rollback $backupRoot "/api/data must be 401" $preVersion
        } catch {
            if ($_.Exception.Response.StatusCode.value__ -ne 401) {
                Invoke-Rollback $backupRoot "/api/data expected 401" $preVersion
            }
        }
    } else {
        Write-Report "mock_dry_run" $true
    }

    $postCounts = Get-DbCounts $dbPath
    Write-Report "post_db_counts" $postCounts
    foreach ($key in @("users","materials","companies","formulas","formula_lines","expenses","weekly_price_reviews","material_price_history","audit_log")) {
        if ($preCounts.$key -ne $postCounts.$key) {
            Invoke-Rollback $backupRoot "Row count changed: $key" $preVersion
        }
    }

    $cpsAfter = Get-Cps8080Snapshot
    Write-Report "cps_8080_after" $cpsAfter
    if ($cpsBefore.pid -and $cpsAfter.pid -and ($cpsBefore.pid -ne $cpsAfter.pid)) {
        Invoke-Rollback $backupRoot "CPS 8080 PID changed" $preVersion
    }

    Write-Report "backup_root" $backupRoot
    Write-Report "DEPLOY_RESULT" "PASS"
    Write-Host "DEPLOY_PASS backup=$backupRoot"
    $Report | ConvertTo-Json -Depth 8
    exit 0
} catch {
    Write-Report "DEPLOY_RESULT" "FAIL"
    Write-Report "error" $_.Exception.Message
    Write-Error $_
    exit 1
}
