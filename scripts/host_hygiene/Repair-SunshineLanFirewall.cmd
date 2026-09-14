@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Repair-SunshineLanFirewall.ps1" %*
exit /b %ERRORLEVEL%
