#
# Stop the FinAlly container on Windows.
#
# A behavioural mirror of scripts/stop_mac.sh: the same checks in the same order,
# the same printed strings, the same exit codes.
#
# Stops and removes the container, and does nothing else. It never deletes,
# moves, truncates or writes to the bind-mounted database directory - a stop that
# reset the user's portfolio is the failure this script exists to make
# impossible, so no path under that directory appears anywhere below.
#
# Running this twice is safe. A second run reports that there is nothing to stop
# and exits 0, which is what keeps stop-then-start a safe pattern.
#
# $LASTEXITCODE is checked after every docker call because
# $ErrorActionPreference governs cmdlet errors, not native executables. Without
# the checks this script would report success while the container was still
# running.
#
# Usage: powershell -NoProfile -File scripts\stop_windows.ps1

$Container = 'finally-app'

$NameFilter = 'name=^' + $Container + '$'

$present = docker ps -a -q --filter $NameFilter
if ($LASTEXITCODE -ne 0) {
    Write-Host 'docker is not available.'
    exit 1
}
if (-not $present) {
    Write-Host "No container named $Container exists. Nothing to stop."
    exit 0
}

docker stop $Container | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to stop $Container."
    exit 1
}

docker rm $Container | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to remove $Container."
    exit 1
}

Write-Host "Stopped and removed container $Container."
