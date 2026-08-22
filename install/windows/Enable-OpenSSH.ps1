# One-time Windows VPS prep so Cloud Agents can deploy without RDP.
# Run in an elevated PowerShell on the VPS (right-click -> Run as Administrator).
#
# After this succeeds, add these Cursor environment secrets once:
#   WINDOWS_VPS_HOST, WINDOWS_VPS_USER, WINDOWS_VPS_PASSWORD
# Optional: WINDOWS_VPS_SSH_PORT (default 22), WINDOWS_VPS_PUBLIC_HOST

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common.ps1")
Assert-Administrator

Write-Step "Enable OpenSSH Server"

$capability = Get-WindowsCapability -Online | Where-Object { $_.Name -like "OpenSSH.Server*" }
if (-not $capability) {
    Write-Err "OpenSSH.Server capability not found on this Windows edition."
    exit 1
}

if ($capability.State -ne "Installed") {
    Write-Info "Installing $($capability.Name)..."
    Add-WindowsCapability -Online -Name $capability.Name | Out-Null
} else {
    Write-Info "OpenSSH Server is already installed"
}

Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
Set-Service -Name ssh-agent -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service ssh-agent -ErrorAction SilentlyContinue

Ensure-FirewallRule -Name "OpenSSH SSH Server (sshd)" -Port 22
Ensure-FirewallRule -Name "OpenBull HTTP" -Port 80
Ensure-FirewallRule -Name "OpenBull HTTPS" -Port 443

Write-Step "SSH is ready"
Write-Info "Service: $((Get-Service sshd).Status) / $((Get-Service sshd).StartType)"
Write-Host ""
Write-Host "Also allow inbound TCP 22 (and 80) in your VPS provider firewall / security group."
Write-Host "Then save WINDOWS_VPS_HOST / USER / PASSWORD in Cursor environment secrets."
Write-Host "This script never needs to be run again unless you rebuild the VPS."
