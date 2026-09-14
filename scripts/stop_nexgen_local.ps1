# Stop NEXGEN local server (PID file + NexGen health verification)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root "logs\nexgen_local.pid"
$Port = if ($env:NEXGEN_PORT) { [int]$env:NEXGEN_PORT } else { 2333 }
$HostAddr = if ($env:NEXGEN_HOST) { $env:NEXGEN_HOST } else { "127.0.0.1" }

function Test-NexGenHealth([string]$BaseUrl) {
    try {
        $resp = Invoke-WebRequest -Uri "$BaseUrl/api/health" -UseBasicParsing -TimeoutSec 3
        return ($resp.Content -match '"app"\s*:\s*"NEXGEN')
    } catch {
        return $false
    }
}

function Get-ListenerPid([int]$TargetPort) {
    $conn = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($conn) { return [int]$conn.OwningProcess }
    return $null
}

$targetPid = $null
if (Test-Path $PidFile) {
    $targetPid = [int](Get-Content $PidFile -Raw).Trim()
}

if (-not $targetPid -or -not (Get-Process -Id $targetPid -ErrorAction SilentlyContinue)) {
    $targetPid = Get-ListenerPid $Port
}

if (-not $targetPid) {
    Write-Host "No NEXGEN listener on port $Port and no valid PID file."
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

$baseUrl = "http://${HostAddr}:$Port"
if (-not (Test-NexGenHealth $baseUrl)) {
    Write-Error "PID $targetPid is not NEXGEN (health check failed on $baseUrl). Refusing to stop."
    exit 1
}

$proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
if ($proc) {
    Stop-Process -Id $targetPid -Force
    Write-Host "NEXGEN stopped. PID=$targetPid Port=$Port"
} else {
    Write-Host "PID $targetPid not found (already stopped)."
}
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
