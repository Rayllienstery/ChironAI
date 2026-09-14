@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-lan-host.ps1" %*
exit /b %ERRORLEVEL%
