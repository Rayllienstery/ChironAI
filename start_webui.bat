@echo off
echo Starting RAG Proxy WebUI server...
echo.
echo WebUI will be available at: http://localhost:8080/webui
echo.
echo Press Ctrl+C to stop the server.
echo.

cd /d %~dp0
python WebUI\rag_proxy.py

pause

