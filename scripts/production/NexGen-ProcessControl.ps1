# NexGen production process / Scheduled Task control (2333 only).
# Dot-source from Stop-NexGen-2333.ps1 and Deploy-NexGen-KG-Fix.ps1

function Get-NexGenHealthJson([string]$BaseUrl) {
    try {
        $resp = Invoke-WebRequest -Uri "$BaseUrl/api/health" -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -ne 200) { return $null }
        return $resp.Content | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-Cps8080Pid {
    $c = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
    return $null
}

function Get-PortListenerPid([int]$PortNum) {
    $c = Get-NetTCPConnection -LocalPort $PortNum -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
    return $null
}

function Test-PortFree([int]$PortNum) {
    return -not (Get-PortListenerPid $PortNum)
}

function Test-NexGenCommandLine([int]$ProcessId, [string]$ProductionRoot) {
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
    } catch {
        return $false
    }
    $cmd = $proc.CommandLine
    if (-not $cmd) { return $false }
    $py = Join-Path $ProductionRoot ".venv\Scripts\python.exe"
    $pyNorm = $py.ToLower()
    $cmdNorm = $cmd.ToLower()
    return ($cmdNorm -like "*python*" -and $cmdNorm -like "*wsgi.py*" -and $cmdNorm -like "*$([IO.Path]::GetFileName($ProductionRoot.ToLower()))*")
}

function Get-VerifiedNexGenListenerPid {
    param(
        [int]$PortNum = 2333,
        [string]$ProductionRoot = "C:\nexgen_maliyet",
        [int]$CpsPid = $(Get-Cps8080Pid)
    )
    $listenerPid = Get-PortListenerPid $PortNum
    if (-not $listenerPid) { return $null }
    if ($CpsPid -and $listenerPid -eq $CpsPid) { return $null }
    $health = Get-NexGenHealthJson "http://127.0.0.1:$PortNum"
    if (-not $health -or $health.app -ne "NEXGEN") { return $null }
    if (-not (Test-NexGenCommandLine $listenerPid $ProductionRoot)) { return $null }
    return $listenerPid
}

function Wait-ScheduledTaskState {
    param(
        [string]$TaskName,
        [string]$DesiredState,
        [int]$TimeoutSec = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task -and $task.State.ToString() -eq $DesiredState) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Wait-PortFreeState {
    param([int]$PortNum = 2333, [int]$TimeoutSec = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortFree $PortNum) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Write-NexGenHealthDiagnostics {
    param(
        $Health,
        [string]$ExpectedVersion,
        [string]$ExpectedDbPath = "C:\nexgen_maliyet\data\nexgen_local.db",
        [hashtable]$Report
    )
    if (-not $Report) { $Report = @{} }
    $Report["POST_HEALTH_STATUS"] = if ($Health) { $Health.status } else { $null }
    $Report["POST_HEALTH_DB_CONNECTED"] = if ($Health) { $Health.db_connected } else { $null }
    $Report["POST_HEALTH_ENVIRONMENT"] = if ($Health) { $Health.environment } else { $null }
    $Report["POST_HEALTH_WSGI"] = if ($Health) { $Health.wsgi_server } else { $null }
    $Report["POST_HEALTH_PORT"] = if ($Health) { $Health.port } else { $null }
    $Report["POST_HEALTH_DB_PATH"] = if ($Health) { $Health.db_path } else { $null }
    $Report["POST_HEALTH_VERSION"] = if ($Health) { $Health.version } else { $null }
    $Report["EXPECTED_VERSION"] = $ExpectedVersion
    $failed = @()
    if (-not $Health) {
        $failed += "health_null"
    } else {
        if ($Health.status -ne "ok") { $failed += "status" }
        if ($Health.db_connected -ne $true) { $failed += "db_connected" }
        if ($Health.environment -ne "production") { $failed += "environment" }
        if ($Health.wsgi_server -ne "waitress") { $failed += "wsgi_server" }
        if ($Health.port -ne 2333) { $failed += "port" }
        if ($Health.db_path -ne $ExpectedDbPath) { $failed += "db_path" }
        if ($Health.version -ne $ExpectedVersion) { $failed += "version" }
    }
    $Report["FAILED_HEALTH_FIELDS"] = ($failed -join ",")
    return $Report
}

function Stop-NexGenTaskSafely {
    param(
        [string]$ProductionRoot = "C:\nexgen_maliyet",
        [string]$TaskName = "NexGen-Maliyet-2333",
        [int]$Port = 2333,
        [int]$TaskReadyTimeoutSec = 30,
        [int]$PortFreeTimeoutSec = 30,
        [switch]$SkipScheduledTask
    )

    $result = [ordered]@{
        task_stopped = $false
        task_ready = $false
        port_free = $false
        stopped_pids = @()
    }

    if (-not $SkipScheduledTask) {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $task) {
            throw "Scheduled Task missing: $TaskName"
        }
        $result["task_state_before"] = $task.State.ToString()
        if ($task.State -eq "Running") {
            Stop-ScheduledTask -TaskName $TaskName
            $result["task_stopped"] = $true
        }
        $ready = Wait-ScheduledTaskState -TaskName $TaskName -DesiredState "Ready" -TimeoutSec $TaskReadyTimeoutSec
        $result["task_ready"] = $ready
        if (-not $ready) {
            $taskNow = Get-ScheduledTask -TaskName $TaskName
            throw "Task $TaskName still $($taskNow.State) after ${TaskReadyTimeoutSec}s"
        }
    }

    $cpsPid = Get-Cps8080Pid
    $deadline = (Get-Date).AddSeconds($PortFreeTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $listenerPid = Get-VerifiedNexGenListenerPid -PortNum $Port -ProductionRoot $ProductionRoot -CpsPid $cpsPid
        if ($listenerPid) {
            Stop-Process -Id $listenerPid -Force
            $result["stopped_pids"] += $listenerPid
            Start-Sleep -Seconds 1
            continue
        }
        $rawPid = Get-PortListenerPid $Port
        if ($rawPid) {
            if ($cpsPid -and $rawPid -eq $cpsPid) {
                throw "Port $Port listener is CPS 8080 PID $rawPid - refusing to stop"
            }
            throw "Port $Port has non-NexGen listener PID $rawPid - refusing to stop"
        }
        $result["port_free"] = $true
        break
    }

    if (-not $result["port_free"]) {
        throw "Port $Port not free after ${PortFreeTimeoutSec}s"
    }
    return $result
}

function Start-NexGenTaskSafely {
    param(
        [string]$TaskName = "NexGen-Maliyet-2333",
        [int]$WaitRunningSec = 30,
        [switch]$SkipScheduledTask
    )
    if ($SkipScheduledTask) { return @{ task_running = $false } }
    Start-ScheduledTask -TaskName $TaskName
    $running = Wait-ScheduledTaskState -TaskName $TaskName -DesiredState "Running" -TimeoutSec $WaitRunningSec
    if (-not $running) {
        $task = Get-ScheduledTask -TaskName $TaskName
        throw "Task $TaskName not Running (state=$($task.State))"
    }
    return @{ task_running = $true }
}
