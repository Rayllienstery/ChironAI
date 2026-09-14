@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Repair-SmbOnVpn.ps1" %*
exit /b %ERRORLEVEL%
