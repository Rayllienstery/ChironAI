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

rem Install front-end dependencies on a clean checkout. npm exposes Vite through
rem node_modules\.bin; without it, npm run build fails with "'vite' is not recognized".
if not exist "node_modules\.bin\vite.cmd" (
    echo Front-end dependencies are not installed; installing from package-lock.json...
    echo.
    if exist package-lock.json (
        call npm.cmd ci
    ) else (
        call npm.cmd install
    )
    if errorlevel 1 (
        echo.
        echo Dependency installation failed. Check npm output above.
        popd
        pause
        exit /b 1
    )
    echo.
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
