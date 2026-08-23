# Start the whole OpenBull stack: Postgres, Redis, backend, website.
# Usage: openbull start
#    or: powershell -ExecutionPolicy Bypass -File Start-OpenBull.ps1

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common.ps1")
Assert-Administrator

Write-Step "Starting OpenBull"
Start-NamedService "postgresql-x64-16"
Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.Name -ne "postgresql-x64-16") { Start-NamedService $_.Name }
}
Start-NamedService "OpenBullRedis"
Start-Sleep -Seconds 1
Start-NamedService "OpenBullBackend"
Start-NamedService "OpenBullCaddy"
Show-OpenBullStatus
Write-Info "OpenBull is started. Open http://127.0.0.1/ or the VPS IP."
