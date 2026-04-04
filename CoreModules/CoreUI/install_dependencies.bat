@echo off
echo Installing npm dependencies...
echo.

call npm.cmd install

if %errorlevel% neq 0 (
    echo.
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Dependencies installed successfully!
echo.
pause

