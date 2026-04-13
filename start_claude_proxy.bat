@echo off
setlocal

set "CHIRON_PROXY_BASE_URL_DEFAULT=http://127.0.0.1:8080"
if not defined CHIRON_PROXY_BASE_URL set "CHIRON_PROXY_BASE_URL=%CHIRON_PROXY_BASE_URL_DEFAULT%"

set "ANTHROPIC_BASE_URL=%CHIRON_PROXY_BASE_URL%"
if not defined ANTHROPIC_AUTH_TOKEN set "ANTHROPIC_AUTH_TOKEN=ollama"
set "ANTHROPIC_API_KEY="

where claude >nul 2>&1
if errorlevel 1 (
  echo ERROR: claude CLI was not found in PATH.
  echo Install Claude Code CLI first, then retry.
  exit /b 1
)

echo Starting Claude Code via ChironAI proxy...
echo Base URL: %ANTHROPIC_BASE_URL%
echo Tip: pass --model ^<your-build-id^> to route through an LLM Proxy build.

claude %*
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
