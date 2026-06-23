@echo off
setlocal
cd /d "%~dp0.."
if not exist "requirements-dev.txt" (
  echo ERROR: requirements-dev.txt not found. Expected repository root parent of scripts\.
  endlocal
  exit /b 1
)

echo Python:
python --version
if errorlevel 1 (
  echo ERROR: python is not in PATH.
  endlocal
  pause
  exit /b 1
)
echo.

echo Upgrading pip...
python -m pip install -U pip
if errorlevel 1 (
  echo pip upgrade failed.
  endlocal
  pause
  exit /b 1
)
echo.

echo Installing from requirements-dev.txt ^(chironai [dev] + editable CoreModules and modules^)...
echo Using PIP_ONLY_BINARY=lxml to prefer wheels on Windows ^(skip source build when possible^).
set "PIP_ONLY_BINARY=lxml"
python -m pip install -r requirements-dev.txt
set "PIP_ONLY_BINARY="
if errorlevel 1 (
  echo.
  echo Install failed. If lxml is the problem, try:
  echo   python -m pip install --only-binary=lxml "lxml^>=6.0.0"
  echo   python -m pip install -r requirements-dev.txt
  endlocal
  pause
  exit /b 1
)

echo.
set "FRONTEND=%CD%\CoreModules\CoreUI"
where npm >nul 2>&1
if errorlevel 1 (
  echo WARNING: npm not found. Skipping CoreUI frontend dependencies.
  echo Install Node.js, then run: CoreModules\CoreUI\install_and_build.bat
) else (
  if not exist "%FRONTEND%\package.json" (
    echo WARNING: CoreUI package.json not found at %FRONTEND%
  ) else (
    echo Installing CoreUI npm dependencies from package-lock.json...
    pushd "%FRONTEND%"
    call npm.cmd ci
    if errorlevel 1 (
      echo npm install failed in CoreModules\CoreUI
      popd
      endlocal
      pause
      exit /b 1
    )
    popd
    echo CoreUI npm dependencies installed.
  )
)

echo.
echo ========================================
echo Done: Python dev stack + CoreUI npm deps.
echo.
echo Optional next steps:
echo   python -m playwright install     ^(crawler / browser automation^)
echo   scripts\build_app.bat            ^(build React frontend^)
echo   docker-compose up -d             ^(start Qdrant^)
echo ========================================
echo.
pause
endlocal
