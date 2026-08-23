# Stop the whole OpenBull stack: website, backend, Redis, Postgres.
# Usage: openbull stop
#    or: powershell -ExecutionPolicy Bypass -File Stop-OpenBull.ps1

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common.ps1")
Assert-Administrator

Write-Step "Stopping OpenBull"
Stop-NamedService "OpenBullCaddy"
Stop-NamedService "OpenBullBackend"
Stop-NamedService "OpenBullRedis"
Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-NamedService $_.Name
}
Show-OpenBullStatus
Write-Info "OpenBull is stopped."
