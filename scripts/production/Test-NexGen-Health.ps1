# NEXGEN production health check
$ErrorActionPreference = "Stop"
$Base = "http://127.0.0.1:2333"
$Lan = "http://192.168.1.48:2333"

function Test-Url([string]$Url) {
    $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8
    return $resp.StatusCode, $resp.Content
}

$code, $body = Test-Url "$Base/api/health"
$h = $body | ConvertFrom-Json
$ok = ($code -eq 200 -and $h.db_connected -and $h.environment -eq "production" -and $h.wsgi_server -eq "waitress" -and $h.debug -eq $false)
Write-Host "LOCAL_HEALTH=$code production=$($h.environment) wsgi=$($h.wsgi_server) debug=$($h.debug) db=$($h.db_connected)"
try {
    $lc, $lb = Test-Url "$Base/login"
    Write-Host "LOCAL_LOGIN=$lc"
} catch { Write-Host "LOCAL_LOGIN=FAIL" }
try {
    $lanc, $lanb = Test-Url "$Lan/login"
    Write-Host "LAN_LOGIN=$lanc"
} catch { Write-Host "LAN_LOGIN=FAIL $($_.Exception.Message)" }
if (-not $ok) { exit 1 }
exit 0
