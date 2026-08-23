# Show whether the whole OpenBull stack is running.
# Usage: openbull status

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common.ps1")
Show-OpenBullStatus
