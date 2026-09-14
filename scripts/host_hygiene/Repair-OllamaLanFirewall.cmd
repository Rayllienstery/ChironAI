@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Repair-OllamaLanFirewall.ps1" %*
exit /b %ERRORLEVEL%
