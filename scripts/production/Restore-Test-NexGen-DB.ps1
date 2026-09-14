# Non-destructive restore test from latest backup
$ErrorActionPreference = "Stop"
$Root = "C:\nexgen_maliyet"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$BackupRoot = Join-Path $Root "backup"
$Latest = Get-ChildItem $BackupRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
if (-not $Latest) { Write-Error "No backup folder"; exit 1 }

$Temp = Join-Path $env:TEMP ("nexgen_restore_test_" + (Get-Date -Format "yyyyMMddHHmmss"))
New-Item -ItemType Directory -Force -Path $Temp | Out-Null
Copy-Item (Join-Path $Latest.FullName "nexgen_local.db") (Join-Path $Temp "nexgen_local.db") -Force
Copy-Item (Join-Path $Latest.FullName ".nexgen_secret") (Join-Path $Temp ".nexgen_secret") -Force -ErrorAction SilentlyContinue

$report = & $Python -c @"
import json, sqlite3
from pathlib import Path
p = Path(r'$Temp') / 'nexgen_local.db'
c = sqlite3.connect(str(p))
cur = c.cursor()
out = {'integrity': cur.execute('PRAGMA integrity_check').fetchone()[0]}
for t in ['users','materials','formulas','formula_lines','expenses']:
    out[t] = cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
neo = cur.execute(\"SELECT profit_rate FROM formulas WHERE id='neo-taban'\").fetchone()
out['neo_profit_rate'] = neo[0]
c.close()
print(json.dumps(out))
"@
Write-Host $report
$j = $report | ConvertFrom-Json
if ($j.integrity -ne 'ok') { exit 1 }
Remove-Item $Temp -Recurse -Force
Write-Host "RESTORE_TEST_PASS"
exit 0
