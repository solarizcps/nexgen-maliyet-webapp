# NEXGEN Maliyet Merkezi - local launcher (Windows, port 2333)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"
$PidFile = Join-Path $LogDir "nexgen_local.pid"
$LockFile = Join-Path $LogDir "nexgen_local.lock"
$StdoutLog = Join-Path $LogDir "nexgen_stdout.log"
$StderrLog = Join-Path $LogDir "nexgen_stderr.log"
$Port = if ($env:NEXGEN_PORT) { [int]$env:NEXGEN_PORT } else { 2333 }
$HostAddr = if ($env:NEXGEN_HOST) { $env:NEXGEN_HOST } else { "127.0.0.1" }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Test-ProcessAlive([int]$ProcessId) {
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Get-PortListener([int]$TargetPort) {
    return Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Wait-HttpOk([string]$Url, [int]$TimeoutSec = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            return $resp.StatusCode
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $null
}

if (Test-Path $PidFile) {
    $existingPid = [int](Get-Content $PidFile -Raw).Trim()
    if (Test-ProcessAlive $existingPid) {
        Write-Host "NEXGEN already running. PID=$existingPid Port=$Port"
        Write-Host "URL: http://${HostAddr}:$Port/"
        exit 0
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

$portUse = Get-PortListener $Port
if ($portUse) {
    $otherPid = $portUse.OwningProcess
    $procName = (Get-Process -Id $otherPid -ErrorAction SilentlyContinue).ProcessName
    Write-Error "Port $Port is in use by PID $otherPid ($procName). Do not touch port 8080 (Solariz CPS)."
    exit 1
}

if (Test-Path $LockFile) {
    Write-Error "Lock file exists: $LockFile"
    exit 1
}

Set-Content -Path $LockFile -Value "$PID $(Get-Date -Format o)" -Encoding UTF8

try {
    $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        $python = (Get-Command python -ErrorAction Stop).Source
    }

    $env:NEXGEN_PORT = "$Port"
    $env:NEXGEN_HOST = $HostAddr

    # Use relative run.py + WorkingDirectory to avoid path-with-spaces split bug
    $null = Start-Process `
        -FilePath $python `
        -ArgumentList @("run.py") `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog

    Start-Sleep -Seconds 2

    $listener = Get-PortListener $Port
    if (-not $listener) {
        Write-Error "Port $Port not LISTENING after start. See $StderrLog"
        if (Test-Path $StderrLog) { Get-Content $StderrLog -Tail 30 | Write-Host }
        exit 1
    }

    $serverPid = [int]$listener.OwningProcess
    Set-Content -Path $PidFile -Value $serverPid -Encoding ASCII

    if (-not (Test-ProcessAlive $serverPid)) {
        Write-Error "Listener PID $serverPid not alive. See $StderrLog"
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        exit 1
    }

    $healthCode = Wait-HttpOk "http://${HostAddr}:$Port/api/health"
    $loginCode = Wait-HttpOk "http://${HostAddr}:$Port/login"
    try {
        Invoke-WebRequest -Uri "http://${HostAddr}:$Port/api/data" -UseBasicParsing -TimeoutSec 3 | Out-Null
        $dataCode = 200
    } catch {
        if ($_.Exception.Response) { $dataCode = [int]$_.Exception.Response.StatusCode } else { $dataCode = 0 }
    }

    Write-Host "NEXGEN started."
    Write-Host "  PID      : $serverPid"
    Write-Host "  URL      : http://${HostAddr}:$Port/"
    Write-Host "  Login    : HTTP $loginCode"
    Write-Host "  Health   : HTTP $healthCode"
    Write-Host "  Data API : HTTP $dataCode (401 expected without session)"
    Write-Host "  Stdout   : $StdoutLog"
    Write-Host "  Stderr   : $StderrLog"
    Write-Host "  PID file : $PidFile"

    if ($healthCode -ne 200 -or $loginCode -ne 200 -or $dataCode -ne 401) {
        Write-Error "HTTP check failed login=$loginCode health=$healthCode data=$dataCode"
        exit 1
    }

    exit 0
}
finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
