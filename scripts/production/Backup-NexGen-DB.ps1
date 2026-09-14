# Daily NexGen DB backup (SQLite online backup)
$ErrorActionPreference = "Stop"
$Root = "C:\nexgen_maliyet"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$BackupScript = Join-Path $Root "scripts\sqlite_online_backup.py"
$Db = Join-Path $Root "data\nexgen_local.db"
$Secret = Join-Path $Root "data\.nexgen_secret"
$Day = Get-Date -Format "yyyy-MM-dd"
$DestDir = Join-Path $Root "backup\$Day"
New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

$Lock = Join-Path $Root "logs\backup.lock"
if (Test-Path $Lock) { Write-Error "Backup already running"; exit 1 }
Set-Content -Path $Lock -Value "$PID $(Get-Date -Format o)"

try {
    $destDb = Join-Path $DestDir "nexgen_local.db"
    $meta = & $Python $BackupScript $Db $destDb | ConvertFrom-Json
    Copy-Item -Path $Secret -Destination (Join-Path $DestDir ".nexgen_secret") -Force
    $meta | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $DestDir "backup_meta.json") -Encoding UTF8
    Write-Host "BACKUP_OK $($meta.sha256)"

    $cutoff = (Get-Date).AddDays(-7)
    Get-ChildItem (Join-Path $Root "backup") -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.CreationTime -lt $cutoff } |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
    exit 0
} finally {
    Remove-Item $Lock -Force -ErrorAction SilentlyContinue
}
