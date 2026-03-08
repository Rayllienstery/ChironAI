@echo off
REM Always run from the folder where this batch file lives (important when started via shortcut)
cd /d "%~dp0"

echo Starting RAG Proxy WebUI server...
echo Working directory: %CD%
echo WebUI will be available at: http://localhost:8080/webui
echo (API: /api/webui/* ; frontend: modules\webui_frontend)
echo.
echo If you updated the code, close this window and run start_webui.bat again to load changes.
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python is not in PATH. Add Python to PATH or run from a dev environment.
  goto :pause_end
)

REM Open browser in the background
start "" "http://localhost:8080/webui"

REM Run Flask server (rag_proxy registers webui_bp so /api/webui/* is available)
python WebUI\rag_proxy.py
if errorlevel 1 (
  echo.
  echo Server exited with an error. Check the message above.
)

:pause_end
pause