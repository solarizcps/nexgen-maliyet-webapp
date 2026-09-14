# Stop verified NEXGEN production process on port 2333
$ErrorActionPreference = "Stop"
$Port = 2333
$HostAddr = "127.0.0.1"

function Test-NexGenHealth([string]$BaseUrl) {
    try {
        $resp = Invoke-WebRequest -Uri "$BaseUrl/api/health" -UseBasicParsing -TimeoutSec 3
        return ($resp.Content -match '"app"\s*:\s*"NEXGEN')
    } catch { return $false }
}

$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $conn) {
    Write-Host "No listener on port $Port"
    exit 0
}

$targetPid = [int]$conn.OwningProcess
$baseUrl = "http://${HostAddr}:$Port"
if (-not (Test-NexGenHealth $baseUrl)) {
    Write-Error "PID $targetPid is not NEXGEN. Refusing to stop."
    exit 1
}

$cpsPid = (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
if ($targetPid -eq $cpsPid) {
    Write-Error "PID matches CPS 8080. Refusing to stop."
    exit 1
}

Stop-Process -Id $targetPid -Force
Write-Host "NEXGEN production stopped PID=$targetPid"
