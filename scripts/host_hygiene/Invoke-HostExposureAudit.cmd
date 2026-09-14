@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Invoke-HostExposureAudit.ps1" %*
exit /b %ERRORLEVEL%
