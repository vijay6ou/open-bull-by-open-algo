# First-time OpenBull install on a Windows VPS.
# Idempotent: existing .env, database, and services are reused.
# Live broker keys are written only when .env does not already exist.
#
# Usage (elevated PowerShell):
#   .\Install-OpenBull.ps1
#   .\Install-OpenBull.ps1 -PublicHost 203.0.113.10
#   .\Install-OpenBull.ps1 -SeedEnvFile C:\secure\openbull.secrets.env

[CmdletBinding()]
param(
    [string]$AppRoot = "",
    [string]$PublicHost = "",
    [string]$SeedEnvFile = "",
    [string]$DbPassword = "",
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common.ps1")
Assert-Administrator

if (-not $AppRoot) { $AppRoot = Get-RepoRoot }
if (-not $PublicHost) {
    if ($env:WINDOWS_VPS_PUBLIC_HOST) { $PublicHost = $env:WINDOWS_VPS_PUBLIC_HOST }
    elseif ($env:WINDOWS_VPS_HOST) { $PublicHost = $env:WINDOWS_VPS_HOST }
    else { $PublicHost = "127.0.0.1" }
}
if (-not $SeedEnvFile) {
    $defaultSeed = Join-Path $PSScriptRoot ".secrets.env"
    if (Test-Path $defaultSeed) { $SeedEnvFile = $defaultSeed }
}

$LogDir = Join-Path $AppRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$EnvPath = Join-Path $AppRoot ".env"

Write-Step "OpenBull Windows install"
Write-Info "App root:    $AppRoot"
Write-Info "Public host: $PublicHost"
Write-Info ".env exists: $(Test-Path $EnvPath)"

# --------------------------------------------------------------------------
# Timezone (Indian markets)
# --------------------------------------------------------------------------
Write-Step "Timezone"
try {
    Set-TimeZone -Id "India Standard Time"
    Write-Info "Timezone set to India Standard Time"
} catch {
    Write-Warn "Could not set timezone: $($_.Exception.Message)"
}

# --------------------------------------------------------------------------
# Chocolatey
# --------------------------------------------------------------------------
Write-Step "Chocolatey"
if (-not (Get-CommandPath "choco")) {
    Write-Info "Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString("https://community.chocolatey.org/install.ps1"))
    Refresh-ProcessPath
}
if (-not (Get-CommandPath "choco")) {
    Write-Err "Chocolatey install failed"
    exit 1
}
Write-Info "choco: $((Get-CommandPath 'choco'))"

function Install-ChocoPackage([string]$Name, [string]$Params = "") {
    $installed = choco list --local-only --exact $Name -r 2>$null
    if ($installed) {
        Write-Info "$Name already installed"
        return
    }
    Write-Info "Installing $Name..."
    if ($Params) {
        choco install $Name -y --no-progress --params $Params
    } else {
        choco install $Name -y --no-progress
    }
    if ($LASTEXITCODE -ne 0) {
        throw "choco install $Name failed with exit $LASTEXITCODE"
    }
    Refresh-ProcessPath
}

Install-ChocoPackage "git"
Install-ChocoPackage "python312"
Install-ChocoPackage "nodejs-lts"
Install-ChocoPackage "nssm"
Install-ChocoPackage "caddy"

# --------------------------------------------------------------------------
# PostgreSQL
# --------------------------------------------------------------------------
Write-Step "PostgreSQL"
if (-not $DbPassword) {
    if (Test-Path $EnvPath) {
        $existingUrl = Get-EnvValue $EnvPath "DATABASE_URL"
        if ($existingUrl -match "postgresql(?:\+[a-z]+)?:\/\/[^:]+:([^@]+)@") {
            $DbPassword = $Matches[1]
        }
    }
    if (-not $DbPassword) { $DbPassword = New-RandomHex 12 }
}

$pgInstalled = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
if (-not $pgInstalled) {
    try {
        Install-ChocoPackage "postgresql16" "/Password:$DbPassword"
    } catch {
        Write-Warn "postgresql16 package failed, trying postgresql"
        Install-ChocoPackage "postgresql" "/Password:$DbPassword"
    }
    Refresh-ProcessPath
} else {
    Write-Info "PostgreSQL service already present: $($pgInstalled.Name)"
}

Get-Service -Name "postgresql*" | ForEach-Object {
    if ($_.StartType -ne "Automatic") { Set-Service -Name $_.Name -StartupType Automatic }
    if ($_.Status -ne "Running") { Start-Service -Name $_.Name }
}

$psql = Get-CommandPath "psql"
if (-not $psql) {
    $psqlCandidates = Get-ChildItem -Path "C:\Program Files\PostgreSQL" -Recurse -Filter "psql.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if ($psqlCandidates) {
        $psql = $psqlCandidates
        Ensure-OnPath (Split-Path $psql)
    }
}
if (-not $psql) {
    Write-Err "psql.exe not found after PostgreSQL install"
    exit 1
}

$env:PGPASSWORD = $DbPassword
$env:PGCLIENTENCODING = "UTF8"
$exists = & $psql -h 127.0.0.1 -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='openbull'" 2>$null
if ($exists -ne "1") {
    Write-Info "Creating database openbull"
    & $psql -h 127.0.0.1 -U postgres -c "CREATE DATABASE openbull OWNER postgres;"
} else {
    Write-Info "Database openbull already exists"
}

# --------------------------------------------------------------------------
# Redis (tporadowski Windows port)
# --------------------------------------------------------------------------
Write-Step "Redis"
$RedisRoot = "C:\ProgramData\openbull-redis"
$RedisExe = Join-Path $RedisRoot "redis-server.exe"
if (-not (Test-Path $RedisExe)) {
    Write-Info "Downloading Redis for Windows..."
    New-Item -ItemType Directory -Force -Path $RedisRoot | Out-Null
    $zip = Join-Path $env:TEMP "redis-win.zip"
    $url = "https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-192.168.1.1.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $RedisRoot -Force
}
Install-WindowsService -Name "OpenBullRedis" -Executable $RedisExe -AppDirectory $RedisRoot `
    -Arguments "--port 6379 --bind 127.0.0.1 --dir `"$RedisRoot`"" `
    -Stdout (Join-Path $LogDir "redis.out.log") -Stderr (Join-Path $LogDir "redis.err.log")
Restart-NamedService "OpenBullRedis"

# --------------------------------------------------------------------------
# uv
# --------------------------------------------------------------------------
Write-Step "uv (Python package manager)"
$uv = Get-CommandPath "uv"
if (-not $uv) {
    Write-Info "Installing uv..."
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    Refresh-ProcessPath
    Ensure-OnPath "$env:USERPROFILE\.local\bin"
    $uv = Get-CommandPath "uv"
}
if (-not $uv) {
    $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
}
if (-not (Test-Path $uv)) {
    Write-Err "uv not found after install"
    exit 1
}
Write-Info "uv: $uv"

# --------------------------------------------------------------------------
# .env: write once, never clobber existing keys
# --------------------------------------------------------------------------
Write-Step "Application .env"
if (Test-Path $EnvPath) {
    Write-Info "Existing .env kept (keys will not be asked for or overwritten)"
} else {
    $example = Join-Path $AppRoot ".env.example"
    if (-not (Test-Path $example)) {
        Write-Err ".env.example missing at $example"
        exit 1
    }
    Copy-Item $example $EnvPath
    $appSecret = New-RandomHex 32
    $pepper = New-RandomHex 32
    Set-EnvValue $EnvPath "APP_SECRET_KEY" $appSecret
    Set-EnvValue $EnvPath "ENCRYPTION_PEPPER" $pepper
    Set-EnvValue $EnvPath "DATABASE_URL" "postgresql+asyncpg://postgres:${DbPassword}@127.0.0.1:5432/openbull"
    Set-EnvValue $EnvPath "FLASK_DEBUG" "false"
    Set-EnvValue $EnvPath "FRONTEND_URL" "http://${PublicHost}"
    Set-EnvValue $EnvPath "CORS_ORIGINS" "http://${PublicHost},http://127.0.0.1,http://localhost"
    Set-EnvValue $EnvPath "WEBSOCKET_URL" "ws://${PublicHost}/ws"
    Set-EnvValue $EnvPath "WEBSOCKET_HOST" "127.0.0.1"
    Set-EnvValue $EnvPath "BACKEND_HOST" "127.0.0.1"
    Set-EnvValue $EnvPath "COOKIE_SECURE" "false"

    $seedKeys = @(
        "BROKER_API_KEY", "BROKER_API_SECRET",
        "BROKER_API_KEY_MARKET", "BROKER_API_SECRET_MARKET",
        "JAINAMXTS_API_KEY", "JAINAMXTS_API_SECRET",
        "JAINAMXTS_API_KEY_MARKET", "JAINAMXTS_API_SECRET_MARKET",
        "JAINAMXTS_CLIENT_ID", "JAINAM_BASE_URL", "JAINAM_ACTIVE_SYMPHONY_SERVER"
    )
    foreach ($key in $seedKeys) {
        $value = [Environment]::GetEnvironmentVariable($key)
        if (-not $value -and $SeedEnvFile) {
            $value = Get-EnvValue $SeedEnvFile $key
        }
        if ($value) { Set-EnvValue $EnvPath $key $value }
    }
    icacls $EnvPath /inheritance:r /grant:r "${env:USERNAME}:(R,W)" | Out-Null
    Write-Info "Wrote $EnvPath once. Future updates will not touch it."
}

# --------------------------------------------------------------------------
# Python deps + migrations
# --------------------------------------------------------------------------
Write-Step "Python dependencies"
Push-Location $AppRoot
try {
    & $uv sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
    $env:PYTHONPATH = $AppRoot
    if (Test-Path (Join-Path $AppRoot "migrate_all.py")) {
        & $uv run python migrate_all.py
    } else {
        & $uv run alembic upgrade head
    }
} finally {
    Pop-Location
}

# --------------------------------------------------------------------------
# Frontend
# --------------------------------------------------------------------------
Write-Step "Frontend"
$frontend = Join-Path $AppRoot "frontend"
if (-not $SkipFrontendBuild -and (Test-Path (Join-Path $frontend "package.json"))) {
    Push-Location $frontend
    try {
        npm install --legacy-peer-deps
        npm run build
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "tsc build failed; falling back to vite build (no typecheck)"
            npx vite build
            if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Warn "Skipping frontend build"
}

# --------------------------------------------------------------------------
# Caddy reverse proxy
# --------------------------------------------------------------------------
Write-Step "Caddy"
$caddy = Get-CommandPath "caddy"
if (-not $caddy) {
    $caddy = "C:\ProgramData\chocolatey\bin\caddy.exe"
}
$caddyTemplate = Join-Path $PSScriptRoot "Caddyfile.template"
$caddyFile = Join-Path $PSScriptRoot "Caddyfile"
$frontendDist = ((Join-Path $frontend "dist") -replace "\\", "/")
$caddyContents = (Get-Content -Path $caddyTemplate -Raw) -replace "__FRONTEND_DIST__", $frontendDist
Set-Content -Path $caddyFile -Value $caddyContents -Encoding UTF8

# --------------------------------------------------------------------------
# Windows services
# --------------------------------------------------------------------------
Write-Step "Windows services"
$pythonUvicornArgs = "run uvicorn backend.main:app --host 127.0.0.1 --port 8000"
Install-WindowsService -Name "OpenBullBackend" -Executable $uv -Arguments $pythonUvicornArgs `
    -AppDirectory $AppRoot `
    -Stdout (Join-Path $LogDir "backend.out.log") -Stderr (Join-Path $LogDir "backend.err.log")

Install-WindowsService -Name "OpenBullCaddy" -Executable $caddy -Arguments "run --config `"$caddyFile`"" `
    -AppDirectory $AppRoot `
    -Stdout (Join-Path $LogDir "caddy.out.log") -Stderr (Join-Path $LogDir "caddy.err.log")

Ensure-FirewallRule -Name "OpenBull HTTP" -Port 80
Ensure-FirewallRule -Name "OpenBull HTTPS" -Port 443

Restart-NamedService "OpenBullRedis"
Restart-NamedService "OpenBullBackend"
Restart-NamedService "OpenBullCaddy"

Start-Sleep -Seconds 5
try {
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 15
    Write-Info "Backend health: $($health.StatusCode)"
} catch {
    try {
        $root = Invoke-WebRequest -Uri "http://127.0.0.1:8000/docs" -UseBasicParsing -TimeoutSec 15
        Write-Info "Backend docs: $($root.StatusCode)"
    } catch {
        Write-Warn "Backend did not answer yet. Check logs\backend.err.log"
    }
}

Write-Step "Install complete"
Write-Info "Open  http://$PublicHost/"
Write-Info "First visit: create the admin account at /setup"
Write-Info "Updates: run Update-OpenBull.ps1 - it will not ask for keys"
Write-Host ""
Write-Host "Also open TCP 80 (and 22) in the VPS provider firewall."
