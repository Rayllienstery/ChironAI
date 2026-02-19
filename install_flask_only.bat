@echo off
echo Installing Flask and essential dependencies for WebUI...
echo.

python -m pip install flask requests qdrant-client langchain-text-splitters

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Flask and dependencies installed successfully!
echo You can now run: .\start_webui.bat
echo ========================================
echo.
pause

