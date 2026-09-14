# Controlled NexGen server deploy orchestrator (KAPI 2-5)
$ErrorActionPreference = "Stop"
$Source = "C:\Users\LENOVO\OneDrive\Desktop\nexgen\nexgen maliyet hesaplama\nexgen-maliyet-webapp"
$Ts = Get-Date -Format "yyyyMMdd_HHmmss"
$Recovery = "C:\NexGen_Maliyet_Recovery\SERVER_DEPLOY_$Ts"
$Staging = "C:\NexGen_Maliyet_Staging\release_$Ts"
$Prod = "C:\nexgen_maliyet"
$Py = (Get-Command python).Source

New-Item -ItemType Directory -Force -Path $Recovery | Out-Null
New-Item -ItemType Directory -Force -Path $Staging | Out-Null

# CPS evidence before
$cpsDb = "C:\Solariz_CPS_SERVER\app\mock_data.db"
$cpsBefore = (Get-FileHash $cpsDb -Algorithm SHA256).Hash
$cps8080Before = (Get-NetTCPConnection -LocalPort 8080 -State Listen | Select-Object -First 1).OwningProcess
"8080_PID=$cps8080Before" | Set-Content (Join-Path $Recovery "cps_8080_before.txt")
$cpsBefore | Set-Content (Join-Path $Recovery "cps_db_sha256_before.txt")

# Online DB backup
$srcDb = Join-Path $Source "data\nexgen_local.db"
$srcSecret = Join-Path $Source "data\.nexgen_secret"
$recDb = Join-Path $Recovery "nexgen_local.db"
$metaJson = & $Py (Join-Path $Source "scripts\sqlite_online_backup.py") $srcDb $recDb
$metaJson | Set-Content (Join-Path $Recovery "db_backup_meta.json") -Encoding UTF8
Copy-Item $srcSecret (Join-Path $Recovery ".nexgen_secret") -Force

# Manifest + config summary
@{
    source = $Source
    timestamp = $Ts
    hostname = $env:COMPUTERNAME
    config = @{
        PORT = 2333
        HOST = "0.0.0.0"
        DB = "C:\nexgen_maliyet\data\nexgen_local.db"
    }
} | ConvertTo-Json | Set-Content (Join-Path $Recovery "config_summary.json") -Encoding UTF8

$hashRows = @()
Get-ChildItem $Source -Recurse -File |
    Where-Object { $_.FullName -notmatch '\\backup\\|\\tests\\|\\screenshots|\\__pycache__|\\logs\\' } |
    ForEach-Object {
        try {
            $hashRows += Get-FileHash $_.FullName -Algorithm SHA256 | Select-Object Path, Hash
        } catch {
            $hashRows += [PSCustomObject]@{ Path = $_.FullName; Hash = "LOCKED_OR_UNREADABLE" }
        }
    }
$hashRows | Export-Csv (Join-Path $Recovery "source_sha256.csv") -NoTypeInformation -Encoding UTF8

@'
ROLLBACK:
1) Disable NexGen-Maliyet-2333 and NexGen-Maliyet-Daily-Backup tasks
2) Run Stop-NexGen-2333.ps1
3) Remove firewall rule NexGen Maliyet 2333 LAN
4) Move C:\nexgen_maliyet to quarantine
5) Restore files from this recovery folder
6) Restart source dev NexGen on 127.0.0.1:2333 if needed
7) Do NOT restart CPS 8080
'@ | Set-Content (Join-Path $Recovery "ROLLBACK.txt") -Encoding UTF8

icacls $Recovery /inheritance:r /grant:r "Administrators:(OI)(CI)F" "SYSTEM:(OI)(CI)F" | Out-Null

# Staging copy
$excludeDirs = @('tests','backup','screenshots_warning_scope','screenshots_port_2333','logs','__pycache__')
robocopy $Source $Staging /E /XD $excludeDirs /XF *.pyc nexgen_local.pid nexgen_local.lock /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy staging failed $LASTEXITCODE" }

New-Item -ItemType Directory -Force -Path (Join-Path $Staging "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Staging "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Staging "backup") | Out-Null
& $Py (Join-Path $Source "scripts\sqlite_online_backup.py") $srcDb (Join-Path $Staging "data\nexgen_local.db") | Set-Content (Join-Path $Staging "staging_db_meta.json") -Encoding UTF8
Copy-Item $srcSecret (Join-Path $Staging "data\.nexgen_secret") -Force
Copy-Item (Join-Path $Source "scripts\production\*.ps1") (Join-Path $Staging "scripts\") -Force
Copy-Item (Join-Path $Source "scripts\sqlite_online_backup.py") (Join-Path $Staging "scripts\") -Force

$recHash = (Get-FileHash $recDb -Algorithm SHA256).Hash
$stgHash = (Get-FileHash (Join-Path $Staging "data\nexgen_local.db") -Algorithm SHA256).Hash
if ($recHash -ne $stgHash) { throw "staging DB sha256 mismatch" }

# Production target
if (Test-Path $Prod) {
    $prev = Join-Path $Recovery "previous_production"
    New-Item -ItemType Directory -Force -Path $prev | Out-Null
    robocopy $Prod $prev /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
}
if (Test-Path $Prod) { Remove-Item $Prod -Recurse -Force }
robocopy $Staging $Prod /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy production failed $LASTEXITCODE" }

Write-Host "RECOVERY=$Recovery"
Write-Host "STAGING=$Staging"
Write-Host "PRODUCTION=$Prod"
Write-Host "STAGING_DB_SHA256=$stgHash"
Write-Host "CPS_DB_SHA256_BEFORE=$cpsBefore"
Write-Host "CPS_8080_PID_BEFORE=$cps8080Before"
