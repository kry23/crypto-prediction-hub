# Remove the CryptoPredictorScheduler scheduled task and (optionally) kill
# any running scheduler process. Idempotent — safe to run when nothing is
# registered.
#
# Usage:
#   pwsh -File scripts\uninstall_windows_scheduler.ps1

$ErrorActionPreference = "Stop"

$taskName = "CryptoPredictorScheduler"

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "Stopping task '$taskName' if running..."
    try {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    } catch {}
    Write-Output "Unregistering task '$taskName'..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Output "Done."
} else {
    Write-Output "No task named '$taskName' is registered. Nothing to do."
}

# Kill any leftover python.exe running run_scheduler.py so the next install
# starts from a clean slate.
$running = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
           Where-Object { $_.CommandLine -like "*run_scheduler*" }
if ($running) {
    Write-Output ""
    Write-Output "Stopping leftover run_scheduler.py process(es):"
    foreach ($proc in $running) {
        Write-Output "  PID $($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}
