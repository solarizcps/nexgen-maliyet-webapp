# NEXGEN Maliyet Merkezi - Production start (Waitress, port 2333)
$ErrorActionPreference = "Stop"

$Root = "C:\nexgen_maliyet"
$LogDir = Join-Path $Root "logs"
$StdoutLog = Join-Path $LogDir "nexgen_stdout.log"
$StderrLog = Join-Path $LogDir "nexgen_stderr.log"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$DbPath = Join-Path $Root "data\nexgen_local.db"
$SecretPath = Join-Path $Root "data\.nexgen_secret"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$env:NEXGEN_HOST = "0.0.0.0"
$env:NEXGEN_PORT = "2333"
$env:NEXGEN_DB_PATH = $DbPath
$env:NEXGEN_SECRET_FILE = $SecretPath
$env:NEXGEN_ENV = "production"
$env:NEXGEN_WSGI = "waitress"
$env:NEXGEN_COOKIE_SECURE = "0"
$env:NEXGEN_COOKIE_SAMESITE = "Lax"
$env:NEXGEN_SESSION_HOURS = "8"

if (-not (Test-Path $Python)) { Write-Error "Missing venv python: $Python"; exit 1 }
if (-not (Test-Path $DbPath)) { Write-Error "Missing DB: $DbPath"; exit 1 }
if (-not (Test-Path $SecretPath)) { Write-Error "Missing secret file: $SecretPath"; exit 1 }

$integrity = & $Python -c "import sqlite3; c=sqlite3.connect(r'$DbPath'); print(c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()"
if ($integrity -ne "ok") { Write-Error "DB integrity_check failed: $integrity"; exit 1 }

$port = [int]$env:NEXGEN_PORT
$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $otherPid = [int]$listener.OwningProcess
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/health" -UseBasicParsing -TimeoutSec 3
        if ($health.Content -notmatch 'NEXGEN') {
            Write-Error "Port $port in use by non-NEXGEN PID $otherPid"
            exit 1
        }
        Write-Host "NEXGEN already listening on $port PID=$otherPid"
        exit 0
    } catch {
        Write-Error "Port $port occupied by PID $otherPid (health check failed)"
        exit 1
    }
}

Set-Location $Root
Write-Host "Starting NEXGEN production Waitress on 0.0.0.0:$port"
& $Python wsgi.py 1>> $StdoutLog 2>> $StderrLog
