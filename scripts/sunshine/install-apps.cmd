@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-apps.ps1" %*
exit /b %ERRORLEVEL%
