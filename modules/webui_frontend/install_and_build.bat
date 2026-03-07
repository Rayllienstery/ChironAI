@echo off
echo Installing npm dependencies...
call npm install
if %errorlevel% neq 0 (
    echo Failed to install dependencies. Please make sure Node.js and npm are installed.
    pause
    exit /b 1
)

echo Building production bundle...
call npm run build
if %errorlevel% neq 0 (
    echo Build failed.
    pause
    exit /b 1
)

echo Build completed successfully!
echo The React app is now ready to be served by the Flask server.
pause

