<#
Stop FinAlly (Windows PowerShell).

Stops and removes the container. It never touches db\, so the portfolio,
watchlist and chat history survive. Delete db\finally.db yourself to reset.

Idempotent: doing nothing is a success when nothing is running.
#>

[CmdletBinding()]
param()

# Native commands report failure through $LASTEXITCODE; a stray line on
# docker's stderr must not abort the script.
$ErrorActionPreference = "Continue"

$Container = "finally"

docker info | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not running, so neither is FinAlly."
    exit 0
}

$existing = docker ps -aq -f "name=^$Container$"
if (-not $existing) {
    Write-Host "FinAlly is not running."
    exit 0
}

docker rm -f $Container | Out-Null
Write-Host "Stopped and removed $Container. The database in db\ is untouched."
