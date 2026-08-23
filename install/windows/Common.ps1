# Shared helpers for OpenBull Windows install / update.
$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) { Write-Host "[INFO] $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Err([string]$Message)  { Write-Host "[ERROR] $Message" -ForegroundColor Red }
function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
    Write-Host ""
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-Administrator {
    if (-not (Test-Administrator)) {
        Write-Err "Run this script from an elevated PowerShell (Run as Administrator)."
        exit 1
    }
}

function Get-RepoRoot {
    if ($PSScriptRoot) {
        return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    }
    return (Get-Location).Path
}

function Get-CommandPath([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Ensure-OnPath([string]$Directory) {
    if (-not $Directory) { return }
    if (-not (Test-Path $Directory)) { return }
    $current = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($current -notlike "*$Directory*") {
        [Environment]::SetEnvironmentVariable("Path", "$current;$Directory", "Machine")
    }
    if ($env:Path -notlike "*$Directory*") {
        $env:Path = "$env:Path;$Directory"
    }
}

function Refresh-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function New-RandomHex([int]$Bytes = 32) {
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return ([System.BitConverter]::ToString($buffer) -replace "-", "").ToLowerInvariant()
}

function Get-EnvValue([string]$Path, [string]$Key) {
    if (-not (Test-Path $Path)) { return $null }
    foreach ($line in Get-Content -Path $Path) {
        if ($line -match "^\s*$Key\s*=\s*(.*)$") {
            return ($Matches[1].Trim().Trim('"'))
        }
    }
    return $null
}

function Set-EnvValue([string]$Path, [string]$Key, [string]$Value) {
    $lines = @()
    $found = $false
    if (Test-Path $Path) {
        foreach ($line in Get-Content -Path $Path) {
            if ($line -match "^\s*$Key\s*=") {
                $lines += "$Key = `"$Value`""
                $found = $true
            } else {
                $lines += $line
            }
        }
    }
    if (-not $found) {
        $lines += "$Key = `"$Value`""
    }
    Set-Content -Path $Path -Value $lines -Encoding UTF8
}

function Ensure-FirewallRule([string]$Name, [int]$Port) {
    $existing = Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue
    if (-not $existing) {
        New-NetFirewallRule -DisplayName $Name -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow | Out-Null
        Write-Info "Opened inbound TCP $Port ($Name)"
    } else {
        Write-Info "Firewall rule already exists: $Name"
    }
}

function Get-NssmPath {
    $nssm = Get-CommandPath "nssm"
    if ($nssm) { return $nssm }
    $candidates = @(
        "C:\ProgramData\chocolatey\bin\nssm.exe",
        "C:\ProgramData\chocolatey\lib\nssm\tools\nssm.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $null
}

function Install-WindowsService {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Executable,
        [string]$Arguments = "",
        [string]$AppDirectory = "",
        [string]$Stdout = "",
        [string]$Stderr = ""
    )
    $nssm = Get-NssmPath
    if (-not $nssm) {
        throw "nssm.exe not found. Install Chocolatey package 'nssm' first."
    }
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) {
        if ($Arguments) {
            & $nssm install $Name $Executable $Arguments
        } else {
            & $nssm install $Name $Executable
        }
    } else {
        & $nssm set $Name Application $Executable | Out-Null
        if ($Arguments) {
            & $nssm set $Name AppParameters $Arguments | Out-Null
        }
    }
    if ($AppDirectory) { & $nssm set $Name AppDirectory $AppDirectory | Out-Null }
    & $nssm set $Name Start SERVICE_AUTO_START | Out-Null
    & $nssm set $Name AppRestartDelay 5000 | Out-Null
    if ($Stdout) { & $nssm set $Name AppStdout $Stdout | Out-Null }
    if ($Stderr) { & $nssm set $Name AppStderr $Stderr | Out-Null }
    & $nssm set $Name AppRotateFiles 1 | Out-Null
    & $nssm set $Name AppRotateBytes 10485760 | Out-Null
}

function Restart-NamedService([string]$Name) {
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Warn "Service $Name is not installed"
        return
    }
    if ($svc.Status -eq "Running") {
        Restart-Service -Name $Name -Force
    } else {
        Start-Service -Name $Name
    }
    Write-Info "$Name is $((Get-Service $Name).Status)"
}

function Get-OpenBullServiceNames {
    $names = @("postgresql-x64-16", "OpenBullRedis", "OpenBullBackend", "OpenBullCaddy")
    $extra = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "postgresql-x64-16" } |
        Select-Object -ExpandProperty Name
    if ($extra) { $names = @($extra) + $names }
    return $names
}

function Start-NamedService([string]$Name) {
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Warn "Service $Name is not installed"
        return
    }
    if ($svc.Status -ne "Running") {
        Start-Service -Name $Name
    }
    Write-Info "$Name is $((Get-Service $Name).Status)"
}

function Stop-NamedService([string]$Name) {
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Warn "Service $Name is not installed"
        return
    }
    if ($svc.Status -ne "Stopped") {
        Stop-Service -Name $Name -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 400
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    Write-Info "$Name is $(if ($svc) { $svc.Status } else { 'missing' })"
}

function Show-OpenBullStatus {
    Write-Host ""
    Write-Host "OpenBull services" -ForegroundColor Cyan
    foreach ($name in (Get-OpenBullServiceNames | Select-Object -Unique)) {
        $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-Host ("  {0,-22} {1}" -f $name, "missing")
        } else {
            Write-Host ("  {0,-22} {1}" -f $name, $svc.Status)
        }
    }
    Write-Host ""
}

function Install-OpenBullCommands {
    param([string]$AppRoot = "C:\openbull")
    $cmdSrc = Join-Path $PSScriptRoot "openbull.cmd"
    if (Test-Path $cmdSrc) {
        Copy-Item $cmdSrc (Join-Path $AppRoot "openbull.cmd") -Force
        Copy-Item $cmdSrc "C:\Windows\openbull.cmd" -Force
    }
    $desktop = [Environment]::GetFolderPath("Desktop")
    if ($desktop) {
        Remove-Item (Join-Path $desktop "OpenBull start.cmd") -Force -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $desktop "OpenBull stop.cmd") -Force -ErrorAction SilentlyContinue
    }
    $build = Join-Path $PSScriptRoot "control\Build-OpenBullControl.ps1"
    if (Test-Path $build) {
        & $build
        Write-Info "OpenBull Control installed (Start Menu + Desktop)"
    }
}
