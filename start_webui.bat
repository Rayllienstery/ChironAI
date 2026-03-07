@echo off
cd /d %~dp0

echo Starting RAG Proxy WebUI server...
echo WebUI will be available at: http://localhost:8080/webui
echo (Frontend source moved to modules\webui_frontend; proxy still in WebUI\rag_proxy.py)

REM Open browser in the background
start "" "http://localhost:8080/webui"

REM Run Flask server in the current console (legacy entry; for modular stack run webui_backend + rag_service separately)
python WebUI\rag_proxy.py