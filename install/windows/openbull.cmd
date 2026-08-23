@echo off
setlocal
set "OPENBULL_SCRIPTS=C:\openbull\install\windows"
if exist "%~dp0Start-OpenBull.ps1" set "OPENBULL_SCRIPTS=%~dp0"
if /I "%~1"=="start"   goto :start
if /I "%~1"=="stop"    goto :stop
if /I "%~1"=="restart" goto :restart
if /I "%~1"=="status"  goto :status
echo Usage: openbull start ^| stop ^| restart ^| status
exit /b 1

:start
powershell -NoProfile -ExecutionPolicy Bypass -File "%OPENBULL_SCRIPTS%Start-OpenBull.ps1"
exit /b %ERRORLEVEL%

:stop
powershell -NoProfile -ExecutionPolicy Bypass -File "%OPENBULL_SCRIPTS%Stop-OpenBull.ps1"
exit /b %ERRORLEVEL%

:restart
powershell -NoProfile -ExecutionPolicy Bypass -File "%OPENBULL_SCRIPTS%Stop-OpenBull.ps1"
if errorlevel 1 exit /b %ERRORLEVEL%
powershell -NoProfile -ExecutionPolicy Bypass -File "%OPENBULL_SCRIPTS%Start-OpenBull.ps1"
exit /b %ERRORLEVEL%

:status
powershell -NoProfile -ExecutionPolicy Bypass -File "%OPENBULL_SCRIPTS%Status-OpenBull.ps1"
exit /b %ERRORLEVEL%
