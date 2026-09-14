# Stop NexGen production: Scheduled Task first, then verified 2333 listener only.
$ErrorActionPreference = "Stop"
$Root = "C:\nexgen_maliyet"
$TaskName = "NexGen-Maliyet-2333"
$Port = 2333

. (Join-Path $PSScriptRoot "NexGen-ProcessControl.ps1")

$cpsPid = Get-Cps8080Pid
Write-Host "CPS_8080_PID=$cpsPid"

$result = Stop-NexGenTaskSafely -ProductionRoot $Root -TaskName $TaskName -Port $Port
Write-Host "TASK_STOPPED=$($result.task_stopped) TASK_READY=$($result.task_ready) PORT_FREE=$($result.port_free)"
if ($result.stopped_pids.Count -gt 0) {
    Write-Host "STOPPED_PIDS=$($result.stopped_pids -join ',')"
} else {
    Write-Host "No NexGen listener on port $Port"
}
exit 0
