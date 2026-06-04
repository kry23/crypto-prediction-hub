# Register the crypto-predictor scheduler as a Windows Scheduled Task.
#
# Trigger: at user logon (no admin needed; runs in user context)
# Action:  powershell -Hidden -Command "cd <project>; .venv\Scripts\python.exe scripts\run_scheduler.py"
# Restart: if the process crashes, retry every 5 min up to 99 times
# Log:     logs\scheduler_persistent.log (appended each run)
#
# Idempotent -- unregisters any existing task with the same name first.
#
# Usage:
#   pwsh -File scripts\install_windows_scheduler.ps1
# After registration, the scheduler starts at next user logon.
# Run scripts\uninstall_windows_scheduler.ps1 to remove.

$ErrorActionPreference = "Stop"

$taskName     = "CryptoPredictorScheduler"
$projectRoot  = (Resolve-Path "$PSScriptRoot\..").Path
$pythonExe    = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runnerScript = Join-Path $projectRoot "scripts\run_scheduler.py"
$logPath      = Join-Path $projectRoot "logs\scheduler_persistent.log"

if (-not (Test-Path $pythonExe)) {
    throw "venv python.exe not found at $pythonExe -- run 'uv venv' + 'uv pip install -e .' first"
}
if (-not (Test-Path $runnerScript)) {
    throw "scripts\run_scheduler.py not found at $runnerScript"
}

# Ensure log dir exists
$logDir = Split-Path $logPath -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# PowerShell action: cd to project, run python, redirect stdout+stderr (append).
# Out-File -Append keeps history across restarts; user can tail it any time.
$psCommand = @"
Set-Location '$projectRoot'
& '$pythonExe' '$runnerScript' 2>&1 | Out-File -FilePath '$logPath' -Append -Encoding utf8
"@

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"$psCommand`""

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive

# Remove existing task with the same name (idempotent re-registration).
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "Removing existing scheduled task '$taskName'..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Write-Output "Registering scheduled task '$taskName' for user '$env:USERNAME'..."
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Run crypto-predictor APScheduler in the background on each user logon. Logs to $logPath." | Out-Null

Write-Output ""
Write-Output "Registered. Summary:"
Write-Output "  Task name : $taskName"
Write-Output "  Action    : $pythonExe $runnerScript"
Write-Output "  Trigger   : At logon of $env:USERNAME"
Write-Output "  Log       : $logPath"
Write-Output ""
Write-Output "To start it now without rebooting:"
Write-Output "  Start-ScheduledTask -TaskName $taskName"
Write-Output ""
Write-Output "To check status:"
Write-Output "  Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo"
Write-Output ""
Write-Output "To stop:"
Write-Output "  Stop-ScheduledTask -TaskName $taskName"
Write-Output ""
Write-Output "To uninstall:"
Write-Output "  pwsh -File scripts\uninstall_windows_scheduler.ps1"
