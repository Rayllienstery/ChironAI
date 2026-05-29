@echo off
REM Run from repo root even when started via shortcut
cd /d "%~dp0"

call scripts\build_app.bat
if errorlevel 1 (
  echo.
  echo [build_and_run] Build failed; server was not started.
  pause
  exit /b 1
)

REM start_webui.bat resolves the configured mutable server port.
timeout /t 3 /nobreak >nul
call start_webui.bat
set "WEBUI_EXIT=%ERRORLEVEL%"
exit /b %WEBUI_EXIT%
