@echo off
setlocal
REM TMRagFetcher: start Docker (if needed), Qdrant, then WebUI.
REM Place in project root. Double-click or run from cmd.

cd /d "%~dp0"

echo [1/3] Checking Docker...
docker info >nul 2>&1
if %errorlevel% neq 0 (
  echo Docker is not running. Starting Docker Desktop...
  if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    echo Waiting for Docker to be ready (up to 90 sec)...
    set /a count=0
    :wait_docker
    timeout /t 5 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% equ 0 goto :docker_ready
    set /a count+=1
    if %count% geq 18 goto :docker_timeout
    goto :wait_docker
    :docker_timeout
    echo Docker did not start in time. Start Docker Desktop manually and run this script again.
    pause
    exit /b 1
    :docker_ready
    echo Docker is ready.
  ) else (
    echo Docker Desktop not found. Install Docker or start it manually, then run this script again.
    pause
    exit /b 1
  )
)

echo [2/3] Checking Qdrant on http://localhost:6333 ...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:6333' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 (
  echo Qdrant is already running at localhost:6333.
) else (
  echo Qdrant not responding. Starting existing container "qdrant"...
  docker start qdrant
  if %errorlevel% neq 0 (
    echo Failed to start container "qdrant". Create it once: docker run -d -p 6333:6333 --name qdrant qdrant/qdrant
    pause
    exit /b 1
  )
  echo Waiting 10 sec for Qdrant...
  timeout /t 10 /nobreak >nul
  echo Qdrant started.
)

echo [3/3] Starting WebUI (tmrag start)...
python tmrag.py start
pause
