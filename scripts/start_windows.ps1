<#
Start FinAlly (Windows PowerShell).

  .\scripts\start_windows.ps1              start, building the image if it is absent
  .\scripts\start_windows.ps1 -Build       force a rebuild first
  .\scripts\start_windows.ps1 -NoBrowser   do not open a browser

Idempotent: any existing FinAlly container is replaced. The database lives in
the bind-mounted db\ directory on the host, so nothing here loses data.
#>

[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$NoBrowser
)

# Native commands report failure through $LASTEXITCODE, which is checked after
# each docker call. A stray line on docker's stderr must not abort the script.
$ErrorActionPreference = "Continue"

$Image = "finally"
$Container = "finally"
$Port = 8000
$Url = "http://localhost:$Port"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

docker info | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not running. Start Docker Desktop and try again."
    exit 1
}

# A fresh clone has no .env; create one so there is no manual first step.
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Add your API keys there if you have them."
}

if (-not (Test-Path "db")) {
    New-Item -ItemType Directory -Path "db" | Out-Null
}

$existingImage = docker images -q $Image
if ($Build -or -not $existingImage) {
    Write-Host "Building image $Image..."
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$existingContainer = docker ps -aq -f "name=^$Container$"
if ($existingContainer) {
    Write-Host "Removing existing container $Container..."
    docker rm -f $Container | Out-Null
}

# Docker accepts forward slashes on Windows and this keeps a path containing
# spaces or backslashes from being mangled by the argument parser.
$Mount = ($Root -replace '\\', '/') + "/db:/app/db"

Write-Host "Starting $Container..."
docker run -d --name $Container -p "${Port}:8000" --env-file .env -v $Mount $Image | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Waiting for the app..."
foreach ($i in 1..60) {
    try {
        Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
        Write-Host "FinAlly is running at $Url"
        Write-Host "Database: $Root\db\finally.db"
        Write-Host "Stop it with .\scripts\stop_windows.ps1"
        if (-not $NoBrowser) { Start-Process $Url }
        exit 0
    } catch {
        Start-Sleep -Seconds 1
    }
}

Write-Host "The app did not become healthy within 60 seconds. Recent logs:"
docker logs --tail 40 $Container
exit 1
