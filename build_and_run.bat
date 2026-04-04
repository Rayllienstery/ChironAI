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

call start_webui.bat
set "WEBUI_EXIT=%ERRORLEVEL%"
if not "%WEBUI_EXIT%"=="0" (
  echo.
  echo [build_and_run] WebUI exited with code %WEBUI_EXIT%.
  pause
)
exit /b %WEBUI_EXIT%
