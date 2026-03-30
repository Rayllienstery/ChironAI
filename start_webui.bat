@echo off
REM Always run from the folder where this batch file lives (important when started via shortcut)
cd /d "%~dp0"

echo Starting RAG Proxy WebUI server...
echo Working directory: %CD%
echo WebUI will be available at: http://localhost:8080/webui
echo (API: /api/webui/* ; frontend: modules\webui_frontend)
echo.
echo If you updated the code, run start_webui.bat again to load changes (this window closes when the server stops).
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python is not in PATH. Add Python to PATH or run from a dev environment.
  exit /b 1
)

REM Stop any process already listening on the configured server port (avoids "address already in use")
echo Stopping any previous WebUI / rag_proxy listener on this port...
python WebUI\kill_listeners_on_config_port.py
echo.

REM Open browser in the background
start "" "http://localhost:8080/webui"

REM Run Flask server (rag_proxy registers webui_bp so /api/webui/* is available)
python WebUI\rag_proxy.py
set WEBUI_EXIT=%ERRORLEVEL%
if not %WEBUI_EXIT%==0 (
  echo.
  echo Server exited with an error. Check the message above.
)
exit /b %WEBUI_EXIT%