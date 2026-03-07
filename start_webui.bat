@echo off
cd /d %~dp0

echo Starting RAG Proxy WebUI server...
echo WebUI will be available at: http://localhost:8080/webui
echo (API: /api/webui/* including open-webui/status; frontend: modules\webui_frontend)
echo.
echo If you updated the code, close this window and run start_webui.bat again to load changes.

REM Open browser in the background
start "" "http://localhost:8080/webui"

REM Run Flask server (rag_proxy registers webui_bp so /api/webui/open-webui/status is available)
python WebUI\rag_proxy.py