@echo off
setlocal

set "CHIRON_PROXY_BASE_URL_DEFAULT=http://127.0.0.1:8080"
if not defined CHIRON_PROXY_BASE_URL set "CHIRON_PROXY_BASE_URL=%CHIRON_PROXY_BASE_URL_DEFAULT%"

set "OPENAI_BASE_URL=%CHIRON_PROXY_BASE_URL%"
set "OPENAI_API_BASE=%CHIRON_PROXY_BASE_URL%"
if not defined OPENAI_API_KEY set "OPENAI_API_KEY=ollama"

where codex >nul 2>&1
if errorlevel 1 (
  echo ERROR: codex CLI was not found in PATH.
  echo Install Codex CLI first, then retry.
  exit /b 1
)

echo Starting Codex via ChironAI proxy...
echo Base URL: %OPENAI_BASE_URL%
echo Tip: pass --model ^<your-build-id^> to route through an LLM Proxy build.

codex %*
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
