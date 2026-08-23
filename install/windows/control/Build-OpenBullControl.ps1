# Build the OpenBull Control app and install Start Menu + Desktop shortcuts.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = "C:\openbull\bin"
$exe = Join-Path $outDir "OpenBullControl.exe"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe" }
if (-not (Test-Path $csc)) { throw "csc.exe not found. .NET Framework 4.8 is required." }

$fw = Split-Path $csc
& $csc /nologo /target:winexe /platform:anycpu /optimize+ `
    /out:$exe `
    /win32manifest:"$here\app.manifest" `
    /r:"$fw\System.Windows.Forms.dll" `
    /r:"$fw\System.Drawing.dll" `
    /r:"$fw\System.ServiceProcess.dll" `
    "$here\OpenBullControl.cs"
if ($LASTEXITCODE -ne 0) { throw "OpenBull Control failed to compile" }

function New-Shortcut([string]$Path, [string]$Target) {
    $dir = Split-Path $Path
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $w = New-Object -ComObject WScript.Shell
    $s = $w.CreateShortcut($Path)
    $s.TargetPath = $Target
    $s.WorkingDirectory = Split-Path $Target
    $s.WindowStyle = 1
    $s.Description = "OpenBull Control"
    $s.IconLocation = "$Target,0"
    $s.Save()
}

New-Shortcut "C:\Users\Public\Desktop\OpenBull.lnk" $exe
$programs = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs"
New-Shortcut (Join-Path $programs "OpenBull.lnk") $exe

$userDesktop = [Environment]::GetFolderPath("Desktop")
if ($userDesktop) {
    New-Shortcut (Join-Path $userDesktop "OpenBull.lnk") $exe
    Remove-Item (Join-Path $userDesktop "OpenBull start.cmd") -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $userDesktop "OpenBull stop.cmd") -Force -ErrorAction SilentlyContinue
}

# Launch with Windows so the tray is always there after reboot.
$run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
New-Item -Path $run -Force | Out-Null
Set-ItemProperty -Path $run -Name "OpenBullControl" -Value "`"$exe`""

Write-Host "OpenBull Control: $exe"
