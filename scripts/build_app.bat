@echo off
rem ==============================================================
rem  scripts/build_app.bat
rem ==============================================================

rem --------------------------------------------------------------------
rem  1. Resolve the absolute path of the repository root.
rem --------------------------------------------------------------------
set "REPO_ROOT=%~dp0.."          rem One directory up from 'scripts'
if \"%REPO_ROOT:~-1%\"==\"\\\" set REPO_ROOT=%REPO_ROOT:~0,-1%

rem --------------------------------------------------------------------
rem  2. Build the React frontend
rem --------------------------------------------------------------------
set "FRONTEND=%REPO_ROOT%\CoreModules\CoreUI"

echo.
echo Building the React app in: %FRONTEND%
echo.

rem Check front‑end folder exists
if not exist "%FRONTEND%" (
    echo ERROR: Front‑end directory not found: %FRONTEND%
    echo Please make sure the repo is checked out correctly.
    pause
    exit /b 1
)

pushd "%FRONTEND%" || (
    echo ERROR: Couldn’t CD into %FRONTEND%.
    pause
    exit /b 1
)

rem Ensure package.json is present
if not exist package.json (
    echo ERROR: package.json missing in %FRONTEND%.
    echo The Node.js project seems to be incomplete.
    popd
    pause
    exit /b 1
)

call npm.cmd run build
set "BUILD_ERR=%ERRORLEVEL%"
popd

if %BUILD_ERR% neq 0 (
    echo.
    echo Build failed. See npm log for details.
    pause
    exit /b 1
)

rem --------------------------------------------------------------------
rem  3. Done (markdown ingestion is Python-only: CoreModules/MdIngestionService)
rem --------------------------------------------------------------------
echo.
echo Build completed successfully!
echo The React app is ready in 'CoreModules\CoreUI\dist/'.
echo.
