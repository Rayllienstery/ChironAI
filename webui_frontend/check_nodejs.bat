@echo off
echo Checking for Node.js installation...
echo.

REM Check if node is in PATH
where node >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Node.js found in PATH
    node --version
    echo.
    
    REM Check if npm is in PATH
    where npm >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] npm found in PATH
        npm --version
        echo.
        echo ========================================
        echo Node.js and npm are ready!
        echo You can now run: npm install
        echo ========================================
    ) else (
        echo [ERROR] npm not found in PATH
        echo Please check Node.js installation.
    )
) else (
    echo [ERROR] Node.js not found in PATH
    echo.
    echo ========================================
    echo Node.js is not installed or not in PATH
    echo.
    echo Please install Node.js from:
    echo https://nodejs.org/
    echo.
    echo Make sure to check "Add to PATH" during installation.
    echo After installation, restart your terminal.
    echo ========================================
)

echo.
pause
