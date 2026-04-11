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
echo ========================================
echo Done: full dev stack from requirements-dev.txt.
echo For crawler / browser automation run: python -m playwright install
echo ========================================
echo.
pause
endlocal
