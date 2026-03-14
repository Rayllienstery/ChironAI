@echo off
echo Installing Python dependencies (without problematic packages)...
echo.

REM Install core dependencies first
echo Installing Flask and core dependencies...
python -m pip install flask requests qdrant-client langchain-text-splitters

if %errorlevel% neq 0 (
    echo Failed to install core dependencies.
    pause
    exit /b 1
)

REM Try to install lxml with pre-built wheel
echo.
echo Attempting to install lxml (pre-built wheel)...
python -m pip install --only-binary=lxml lxml

if %errorlevel% neq 0 (
    echo.
    echo Warning: lxml installation failed. This may affect other functionality.
    echo WebUI should still work without it.
    echo.
)

REM Install other dependencies
echo.
echo Installing other dependencies...
python -m pip install html2text playwright

if %errorlevel% neq 0 (
    echo.
    echo Some optional dependencies failed to install.
    echo WebUI core functionality should still work.
    echo.
)

echo.
echo ========================================
echo Core dependencies installed!
echo WebUI should be functional now.
echo ========================================
echo.
pause

