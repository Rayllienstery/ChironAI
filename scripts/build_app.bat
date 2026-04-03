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
set "FRONTEND=%REPO_ROOT%\modules\webui_frontend"

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
rem  3. Build the Swift `md_ingest` module
rem --------------------------------------------------------------------
echo.
echo Building Swift md_ingest module...
echo.

rem Ensure 'bin' output directory exists
if not exist "bin" mkdir "bin"

rem --------------------------------------------------------------------
rem  3a. Make sure Swift is on PATH (install if needed)
rem --------------------------------------------------------------------
set "SWIFT_JUST_INSTALLED=0"

where swift >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Swift not found. Installing Swift for Windows…
    winget install --id Swift.Toolchain -e --accept-package-agreements --accept-source‑agreements --silent 2>nul

    if %ERRORLEVEL% neq 0 (
        echo winget install failed or is unavailable. Downloading Swift installer…
        set "SWIFT_INSTALLER=%TEMP%\swift-windows-installer.exe"
        set "SWIFT_URL=https://download.swift.org/swift-6.2.4-release/windows10/swift-6.2.4-RELEASE/swift-6.2.4-RELEASE-windows10.exe"

        powershell -NoProfile -ExecutionPolicy Bypass `
            -Command ^
            "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; `
            Invoke-WebRequest -Uri '%SWIFT_URL%' -OutFile '%SWIFT_INSTALLER%' -UseBasicParsing } `
            catch { Write-Host $_.Exception.Message; exit 1 }"

        if exist "%SWIFT_INSTALLER%" (
            echo Running Swift installer (may require confirmation)…
            start /wait "" "%SWIFT_INSTALLER%" /passive
            del /q "%SWIFT_INSTALLER%" 2>nul
        ) else (
            echo Download failed. Please install Swift manually: https://swift.org/install/windows/
            pause
            exit /b 1
        )
    )
    set "SWIFT_JUST_INSTALLED=1"
)

rem --------------------------------------------------------------------
rem  3b. Build the Swift package
rem --------------------------------------------------------------------
set "SWIFT_PATH=%REPO_ROOT%\swift-md-ingest"

if not exist "%SWIFT_PATH%" (
    echo ERROR: Swift package not found: %SWIFT_PATH%
    pause
    exit /b 1
)

pushd "%SWIFT_PATH%" || (
    echo ERROR: Couldn’t CD into %SWIFT_PATH%.
    pause
    exit /b 1
)

if "%SWIFT_JUST_INSTALLED%"=="1" (
    echo Building Swift with refreshed PATH…
    powershell -NoProfile -Command ^
    "Set-Location -LiteralPath '%CD%'; `
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + `
    [Environment]::GetEnvironmentVariable('Path','User'); `
    & swift build -c release --package-path '.'; `
    exit $LASTEXITCODE"
) else (
    swift build -c release --package-path "."
)

set "SWIFT_ERR=%ERRORLEVEL%"
popd

if %SWIFT_ERR% neq 0 (
    echo.
    echo Swift md_ingest build failed.
    if "%SWIFT_JUST_INSTALLED%"=="1" (
        echo If Swift was just installed, re‑open this window and run build_app.bat again.
    )
    pause
    exit /b 1
)

rem --------------------------------------------------------------------
rem  4. Copy the built binary into 'bin'
rem --------------------------------------------------------------------
rem First try the .exe version (Windows)
copy /y "%SWIFT_PATH%\.build\release\swift-md-ingest.exe" "bin\swift-md-ingest.exe" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    rem Fall back to the non‑exe variant (e.g. other platforms)
    copy /y "%SWIFT_PATH%\.build\release\swift-md-ingest" "bin\swift-md-ingest" >nul 2>&1
)

rem --------------------------------------------------------------------
rem  5. Success message
rem --------------------------------------------------------------------
echo.
echo Build completed successfully!
echo The React app is ready in 'modules\webui_frontend\dist/'.
echo The Swift binary is in the 'bin/' directory.
echo.
