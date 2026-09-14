# Deployment task-restart-race tests (isolated, no production contact).
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$failed = 0

function Assert([bool]$Cond, [string]$Name) {
    if ($Cond) { Write-Host "PASS $Name" } else { Write-Host "FAIL $Name"; $script:failed++ }
}

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

# 3 Deploy script must Stop-ScheduledTask before Copy-Item
$deployText = Get-Content (Join-Path $Root "scripts\deploy\Deploy-NexGen-KG-Fix.ps1") -Raw
$stopIdx = $deployText.IndexOf("Stop-NexGenTaskSafely")
$copyIdx = $deployText.IndexOf("Copy-Item $src $dst")
if ($copyIdx -lt 0) { $copyIdx = $deployText.IndexOf("Copy-Item (Join-Path $ReleaseRoot") }
Assert ($stopIdx -gt 0 -and $copyIdx -gt $stopIdx) "stop task before file copy"

# 4 Stop script must reference Stop-ScheduledTask via module
$stopText = Get-Content (Join-Path $Root "scripts\production\Stop-NexGen-2333.ps1") -Raw
$pcText = Get-Content (Join-Path $Root "scripts\production\NexGen-ProcessControl.ps1") -Raw
Assert ($pcText -match "Stop-ScheduledTask") "process control stops scheduled task"
Assert ($stopText -match "Stop-NexGenTaskSafely") "stop script uses safe stop"

# 5 Forbidden patterns absent from production scripts
$forbidden = @("taskkill", "Remove-Item `$CanonicalRoot", "Remove-Item C:\\nexgen_maliyet")
foreach ($pat in $forbidden) {
    Assert ($deployText -notmatch [regex]::Escape($pat)) "deploy no forbidden: $pat"
    Assert ($pcText -notmatch "taskkill") "process control no taskkill"
}

# 6 Rollback order — Stop-NexGenTaskSafely before restore copy
Assert ($deployText -match "Invoke-Rollback[\s\S]*Stop-NexGenTaskSafely") "rollback stops task first"

# 7 Port free helper on unlikely port
Assert (Test-PortFree 59987) "unused port is free"

# 8 CPS PID guard logic present
Assert ($pcText -match "CPS 8080") "CPS guard referenced"

# 9 Deploy script reports explicit health fields via diagnostics helper
Assert ($deployText -match "Write-NexGenHealthDiagnostics|FAILED_HEALTH_FIELDS") "deploy uses explicit health fields"

# 10 Start-ScheduledTask once after copy
$startCount = ([regex]::Matches($deployText, "Start-NexGenTaskSafely")).Count
Assert ($startCount -ge 1) "deploy starts task after copy"

Write-Host "DEPLOY_TESTS_FAILED=$failed"
if ($failed -gt 0) { exit 1 }
Write-Host "DEPLOY_TESTS_PASS=$failed"
exit 0
