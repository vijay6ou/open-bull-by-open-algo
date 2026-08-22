# Update OpenBull on this Windows VPS without asking for keys.
# Existing C:\openbull\.env is backed up and restored; never overwritten.
#
# Usage (elevated PowerShell):
#   .\Update-OpenBull.ps1
#   .\Update-OpenBull.ps1 -SkipGitPull

[CmdletBinding()]
param(
    [string]$AppRoot = "",
    [switch]$SkipGitPull,
    [switch]$FlushRedis
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common.ps1")
Assert-Administrator

if (-not $AppRoot) { $AppRoot = Get-RepoRoot }
$EnvPath = Join-Path $AppRoot ".env"
$LogDir = Join-Path $AppRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $AppRoot "backups\$stamp"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

Write-Step "OpenBull Windows update"
Write-Info "App root: $AppRoot"

if (-not (Test-Path $EnvPath)) {
    Write-Err ".env is missing at $EnvPath. Run Install-OpenBull.ps1 first."
    exit 1
}
Copy-Item $EnvPath (Join-Path $BackupDir ".env")
Write-Info "Backed up .env to $BackupDir"

if (-not $SkipGitPull) {
    Write-Step "Pull latest code"
    Push-Location $AppRoot
    try {
        git config --global --add safe.directory $AppRoot 2>$null
        if (Test-Path (Join-Path $AppRoot ".git")) {
            git fetch origin
            $branch = (git rev-parse --abbrev-ref HEAD).Trim()
            if (-not $branch -or $branch -eq "HEAD") { $branch = "main" }
            git pull origin $branch
        } else {
            Write-Warn "No .git directory - skipping pull (files were synced by remote-deploy)"
        }
    } finally {
        Pop-Location
    }
    if (Test-Path (Join-Path $BackupDir ".env")) {
        Copy-Item (Join-Path $BackupDir ".env") $EnvPath -Force
        Write-Info "Restored .env after pull"
    }
} else {
    Write-Info "SkipGitPull: using the files already on disk"
}

$uv = Get-CommandPath "uv"
if (-not $uv) { $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
if (-not (Test-Path $uv)) {
    Write-Err "uv not found. Run Install-OpenBull.ps1 first."
    exit 1
}

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

Write-Step "Frontend rebuild"
$frontend = Join-Path $AppRoot "frontend"
if (Test-Path (Join-Path $frontend "package.json")) {
    Push-Location $frontend
    try {
        npm install --legacy-peer-deps
        npm run build
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "tsc build failed; falling back to vite build"
            npx vite build
            if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
        }
    } finally {
        Pop-Location
    }
}

$caddyTemplate = Join-Path $PSScriptRoot "Caddyfile.template"
if (Test-Path $caddyTemplate) {
    $caddyFile = Join-Path $PSScriptRoot "Caddyfile"
    $frontendDist = ((Join-Path $frontend "dist") -replace "\\", "/")
    $caddyContents = (Get-Content -Path $caddyTemplate -Raw) -replace "__FRONTEND_DIST__", $frontendDist
    Set-Content -Path $caddyFile -Value $caddyContents -Encoding UTF8
}

if ($FlushRedis) {
    $redisCli = "C:\ProgramData\openbull-redis\redis-cli.exe"
    if (Test-Path $redisCli) {
        & $redisCli -n 0 FLUSHDB
        Write-Info "Redis DB 0 flushed"
    }
}

Write-Step "Restart services"
Restart-NamedService "OpenBullRedis"
Restart-NamedService "OpenBullBackend"
Restart-NamedService "OpenBullCaddy"

Write-Step "Update complete"
Write-Info ".env was not changed"
Write-Info "Backup: $BackupDir"
Write-Host "Logs: $LogDir\backend.err.log"
