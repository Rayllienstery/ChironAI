@echo off
REM Always run from the folder where this batch file lives (important when started via shortcut)
cd /d "%~dp0"

echo Starting ChironAI server...
echo Working directory: %CD%

set "PYTHONPATH=%CD%;%CD%\modules\webui_backend;%PYTHONPATH%"

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python is not in PATH. Add Python to PATH or run from a dev environment.
  exit /b 1
)

for /f "usebackq delims=" %%U in (`python -m webui_backend.print_server_url`) do set "WEBUI_URL=%%U"
if not defined WEBUI_URL set "WEBUI_URL=http://localhost:8080/webui"

echo WebUI will be available at: %WEBUI_URL%
echo (API: /api/webui/* ; frontend: CoreModules\CoreUI)
echo.
echo If you updated the code, run start_webui.bat again to load changes (this window closes when the server stops).
echo.

REM Stop any process already listening on known server ports (avoids "address already in use")
echo Stopping any previous WebUI / rag_proxy listener on known ports...
python -m webui_backend.kill_listeners_on_config_port
echo Listeners cleared.
echo.

REM Open browser in the background
echo Opening browser at %WEBUI_URL%
start "" "%WEBUI_URL%"

echo Starting backend (first start can take 10-30s while modules load)...
echo.

REM Run Flask server (rag_proxy registers webui_bp so /api/webui/* is available)
python -m webui_backend.rag_proxy
set WEBUI_EXIT=%ERRORLEVEL%
if not %WEBUI_EXIT%==0 (
  echo.
  echo Server exited with an error. Check the message above.
)
exit /b %WEBUI_EXIT%
pause
