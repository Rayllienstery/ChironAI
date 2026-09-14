@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-HostExposureAuditTask.ps1" %*
exit /b %ERRORLEVEL%
