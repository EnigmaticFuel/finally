#
# Start the FinAlly container on Windows.
#
# A behavioural mirror of scripts/start_mac.sh: the same checks in the same
# order, the same printed strings, the same exit codes. The container lifecycle
# contract is the thing being implemented; this file and start_mac.sh are two
# platform variants of it, so a change to one belongs in the other.
#
# Builds finally-app:latest when it is missing or when --build is passed, prints
# the image tag and the timestamp that image was built, runs one container, waits
# for GET /api/health to return 200, then prints the URL.
#
# Running this twice is safe. A second run reports that the container is already
# running and exits 0 without stopping, restarting or recreating anything, so the
# SSE stream and every ticker's session open price survive.
#
# Targets Windows PowerShell 5.1, the only host installed on the development
# machine. That rules out the ternary operator, null-coalescing, and
# Invoke-WebRequest's -SkipHttpErrorCheck, none of which exist in 5.1. It is also
# why the readiness gate must never be written as bare curl: in 5.1 that name is
# an alias for Invoke-WebRequest and its flags would be parsed as PowerShell
# parameters.
#
# $LASTEXITCODE is checked after every docker call because
# $ErrorActionPreference governs cmdlet errors, not native executables. Without
# the checks this script would sail past a failed docker run and print the URL
# for a container that does not exist.
#
# Usage: powershell -NoProfile -File scripts\start_windows.ps1 [--build]

$Image = 'finally-app:latest'
$Container = 'finally-app'
$Url = 'http://localhost:8000'
# The gate polls the address the container is actually published on. localhost
# resolves to ::1 first on a dual-stack host, and the publish is IPv4 loopback
# only, so a poll of localhost pays a connect-failure wait on every attempt
# before falling back - measured at 2231ms against 145ms here, which is longer
# than the per-attempt timeout and so never succeeds. The user still gets
# http://localhost:8000, which their browser resolves with the same fallback.
$HealthUrl = 'http://127.0.0.1:8000/api/health'
$ReadyTimeoutSeconds = 60

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$Build = 0
if ($args.Count -ge 1 -and $args[0] -eq '--build') {
    $Build = 1
}

# Anchored filter plus -q: the emptiness of the output is the test. docker ps
# output is never parsed, because the name filter is a substring match and an
# unanchored one would also match a container called finally-app-check.
$NameFilter = 'name=^' + $Container + '$'

$running = docker ps -q --filter $NameFilter --filter status=running
if ($LASTEXITCODE -ne 0) {
    Write-Host 'docker is not available.'
    exit 1
}
if ($running) {
    Write-Host "Container $Container is already running."
    Write-Host $Url
    exit 0
}

$present = docker ps -a -q --filter $NameFilter
if ($LASTEXITCODE -ne 0) {
    Write-Host 'docker is not available.'
    exit 1
}
if ($present) {
    docker rm $Container | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to remove the stopped container $Container."
        exit 1
    }
}

$existing = docker images -q $Image
if ($LASTEXITCODE -ne 0) {
    Write-Host 'docker is not available.'
    exit 1
}
if (-not $existing -or $Build -eq 1) {
    docker build -t $Image $RepoRoot
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to build $Image."
        exit 1
    }
}

$built = docker image inspect $Image --format '{{.Created}}'
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to inspect $Image."
    exit 1
}
Write-Host "Image:      $Image"
Write-Host "Built:      $built"

docker run -d --name $Container -p 127.0.0.1:8000:8000 -v "$RepoRoot\db:/app/db" --env-file "$RepoRoot\.env" $Image | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to start $Container. If port 8000 is already in use, run scripts\stop_windows.ps1 and try again."
    exit 1
}

# Gate on the status code alone. newest_price_age_seconds is null until the
# first price arrives, so a gate that waited for it would hang on a cold start.
# The empty catch is required control flow, not a swallowed error: in 5.1 a
# non-2xx response throws, and an endpoint that is legitimately not ready yet
# must not end the loop. The deadline below owns the failure path.
$deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
while ($true) {
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { break }
    } catch { }
    if ((Get-Date) -ge $deadline) {
        Write-Host "Timed out after ${ReadyTimeoutSeconds}s waiting for $HealthUrl"
        docker logs --tail 40 $Container
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Container logs could not be read."
        }
        exit 1
    }
    Start-Sleep -Seconds 1
}

Write-Host $Url
