@echo off
REM ChironAI: start Docker (if needed), Qdrant, then RAG proxy.
REM Place in project root. Double-click or run from cmd.

REM If launched by double-click, restart in a persistent window
if "%~1"=="" (
  cmd /k "%~f0" _restarted
  exit /b
)

setlocal enabledelayedexpansion

REM Ensure we're in the script directory
cd /d "%~dp0" 2>nul
if not exist "%~dp0tmrag.py" (
  echo ERROR: Cannot find tmrag.py in script directory: %~dp0
  echo Please ensure Start_Proxy.cmd is in the project root directory.
  echo.
  pause
  exit /b 1
)

echo ========================================
echo ChironAI - Starting RAG Proxy
echo ========================================
echo.

REM [1/3] Check Docker
echo [1/3] Checking Docker...
docker --version >nul 2>&1
set DOCKER_VER=!errorlevel!
if not "!DOCKER_VER!"=="0" (
  echo ERROR: Docker command not found or not accessible.
  echo Please install Docker Desktop and ensure it is in your PATH.
  echo.
  pause
  exit /b 1
)

docker info >nul 2>&1
set DOCKER_CHECK=!errorlevel!
if not "!DOCKER_CHECK!"=="0" goto :docker_not_running
echo Docker is running.
goto :docker_done

:docker_not_running
echo Docker is not running. Attempting to start Docker Desktop...
set "DOCKER_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"
if not exist "!DOCKER_EXE!" goto :docker_not_found
start "" "!DOCKER_EXE!"
echo Waiting for Docker to be ready (up to 90 seconds)...
set /a count=0
:wait_docker_proxy
timeout /t 5 /nobreak >nul 2>nul
docker info >nul 2>&1
if "!errorlevel!"=="0" goto :docker_ready_proxy
set /a count+=1
if !count! geq 18 goto :docker_timeout_proxy
goto :wait_docker_proxy

:docker_timeout_proxy
echo.
echo ERROR: Docker did not start within 90 seconds.
echo Please start Docker Desktop manually and run this script again.
echo.
pause
exit /b 1

:docker_ready_proxy
echo Docker is ready.
goto :docker_done

:docker_not_found
echo ERROR: Docker Desktop executable not found at expected location.
echo Please install Docker Desktop or start it manually, then run this script again.
echo.
pause
exit /b 1

:docker_done

echo.

REM [2/3] Check Qdrant
echo [2/3] Checking Qdrant on http://localhost:6333 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:6333' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop; exit 0 } catch { exit 1 }" >nul 2>&1
set QDRANT_CHECK=!errorlevel!
if "!QDRANT_CHECK!"=="0" goto :qdrant_ok
echo Qdrant is not responding. Attempting to start container "qdrant"...
docker start qdrant >nul 2>&1
set DOCKER_START=!errorlevel!
if not "!DOCKER_START!"=="0" goto :qdrant_fail
echo Waiting 10 seconds for Qdrant to start...
timeout /t 10 /nobreak >nul 2>nul
echo Qdrant started.
goto :qdrant_done

:qdrant_fail
echo.
echo ERROR: Failed to start Qdrant container "qdrant".
echo.
echo To create the container, run:
echo   docker run -d -p 6333:6333 --name qdrant qdrant/qdrant
echo.
pause
exit /b 1

:qdrant_ok
echo Qdrant is already running at localhost:6333.
:qdrant_done

echo.

REM [3/3] Start RAG proxy
echo [3/3] Starting RAG proxy (tmrag proxy)...
python --version >nul 2>&1
set PY_VER=!errorlevel!
if not "!PY_VER!"=="0" (
  echo ERROR: Python not found or not accessible.
  echo Please install Python and ensure it is in your PATH.
  echo.
  pause
  exit /b 1
)

if not exist "tmrag.py" (
  echo ERROR: tmrag.py not found in current directory.
  echo Please ensure Start_Proxy.cmd is in the project root directory.
  echo.
  pause
  exit /b 1
)

echo.
echo ========================================
echo Starting RAG proxy server...
echo ========================================
echo The window will remain open to show server logs.
echo Press Ctrl+C to stop the server.
echo.
echo.

python tmrag.py proxy
set PROXY_EXIT_CODE=!errorlevel!

echo.
echo ========================================
if not "!PROXY_EXIT_CODE!"=="0" (
  echo ERROR: RAG proxy failed to start
  echo Exit code: !PROXY_EXIT_CODE!
  echo ========================================
  echo Check the error messages above for details.
) else (
  echo RAG proxy stopped normally.
  echo ========================================
)
echo.
pause
exit /b !PROXY_EXIT_CODE!
