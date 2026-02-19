@echo off
echo Building React app...
echo.

call npm.cmd run build

if %errorlevel% neq 0 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build completed successfully!
echo The React app is ready in the dist/ folder.
echo.
pause

