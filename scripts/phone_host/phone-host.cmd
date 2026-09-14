@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0phone-host.ps1" %*
exit /b %ERRORLEVEL%
