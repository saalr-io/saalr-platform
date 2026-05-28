<#
.SYNOPSIS
    Start the Saalr local dev stack: Docker Postgres+Redis, the FastAPI API, and the web dev server.

.DESCRIPTION
    Brings up the database (and waits for it), applies migrations, starts the API in the
    background, then runs the Vite web dev server in the foreground. Press Ctrl+C to stop —
    the API is shut down automatically when the web server exits.

.PARAMETER SkipDb       Don't start/wait for the Docker database (assume it's already up).
.PARAMETER SkipMigrate  Don't run `alembic upgrade head`.
.PARAMETER NoWeb        Start the DB + API only (no web dev server); blocks until Ctrl+C.
.PARAMETER ApiPort      Port for the API (default 8000).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/start.ps1
    powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -SkipDb -SkipMigrate
#>
[CmdletBinding()]
param(
    [switch]$SkipDb,
    [switch]$SkipMigrate,
    [switch]$NoWeb,
    [int]$ApiPort = 8000
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Compose = @('compose', '-f', 'infra/docker/docker-compose.yml')

if (-not $env:ADMIN_DATABASE_URL) {
    $env:ADMIN_DATABASE_URL = 'postgresql+asyncpg://postgres:postgres@localhost:5432/saalr'
}
if (-not $env:APP_DATABASE_URL) {
    $env:APP_DATABASE_URL = 'postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr'
}

function Need($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "$name not found on PATH" }
}
Need uv
if (-not $NoWeb) { Need pnpm }

New-Item -ItemType Directory -Force -Path (Join-Path $Root 'logs') | Out-Null

if (-not $SkipDb) {
    Need docker
    Write-Host 'Starting Docker Postgres + Redis...' -ForegroundColor Cyan
    & docker @Compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
    Write-Host 'Waiting for Postgres' -NoNewline
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        & docker @Compose exec -T postgres pg_isready -U postgres -d saalr *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2; Write-Host '.' -NoNewline
    }
    if (-not $ready) { throw 'Postgres did not become ready' }
    Write-Host ' ready' -ForegroundColor Green
}

if (-not $SkipMigrate) {
    Write-Host 'Applying migrations (alembic upgrade head)...' -ForegroundColor Cyan
    & uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'alembic upgrade failed' }
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$apiLog = Join-Path $Root "logs/api-$stamp.log"
Write-Host "Starting API on http://localhost:$ApiPort  (log: $apiLog)" -ForegroundColor Cyan
$api = Start-Process -FilePath 'uv' -PassThru -NoNewWindow `
    -ArgumentList @('run', 'uvicorn', 'saalr_api.main:create_app', '--factory', '--host', '127.0.0.1', '--port', "$ApiPort") `
    -RedirectStandardOutput $apiLog -RedirectStandardError "$apiLog.err"

try {
    for ($i = 0; $i -lt 20; $i++) {
        try { Invoke-WebRequest "http://localhost:$ApiPort/healthz" -UseBasicParsing -TimeoutSec 2 | Out-Null; break }
        catch { Start-Sleep -Seconds 1 }
    }
    Write-Host "API ready: http://localhost:$ApiPort/healthz  (Swagger: /docs)" -ForegroundColor Green

    if ($NoWeb) {
        Write-Host "API running (PID $($api.Id)). Press Ctrl+C to stop." -ForegroundColor Yellow
        Wait-Process -Id $api.Id
    }
    else {
        Write-Host 'Starting web dev server (Vite) - it will print its URL (5173 or next free).' -ForegroundColor Cyan
        Write-Host 'Press Ctrl+C to stop the web server and the API.' -ForegroundColor Yellow
        & pnpm -C (Join-Path $Root 'apps/web') dev
    }
}
finally {
    if ($api -and -not $api.HasExited) {
        Write-Host "`nStopping API (PID $($api.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    }
}
