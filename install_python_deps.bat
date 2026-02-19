@echo off
echo Installing Python dependencies...
echo.

REM Check if pip is available
python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip is not available. Please install Python with pip.
    pause
    exit /b 1
)

echo Installing dependencies from WebUI\requirements.txt...
python -m pip install -r WebUI\requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install some dependencies.
    echo Please check the error messages above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Dependencies installed successfully!
echo ========================================
echo.
pause

