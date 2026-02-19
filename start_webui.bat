@echo off
cd /d %~dp0

echo Starting RAG Proxy WebUI server...
echo WebUI will be available at: http://localhost:8080/webui

REM Open browser in the background
start "" "http://localhost:8080/webui"

REM Run Flask server in the current console
python WebUI\rag_proxy.py