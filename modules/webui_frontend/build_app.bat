@echo off
echo Building React app and Swift md_ingest module...
echo.

call npm.cmd run build

if %errorlevel% neq 0 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Building Swift md_ingest module...
echo.

pushd "%~dp0\..\.."
if not exist "bin" (
    mkdir "bin"
)

rem Check if Swift is in PATH
set "SWIFT_JUST_INSTALLED=0"
where swift >nul 2>&1
if %errorlevel% neq 0 (
    echo Swift not found. Installing Swift for Windows...
    echo.
    winget install --id Swift.Toolchain -e --accept-package-agreements --accept-source-agreements --silent 2>nul
    if %errorlevel% neq 0 (
        echo winget install failed or winget not available. Downloading Swift installer...
        set "SWIFT_INSTALLER=%TEMP%\swift-windows-installer.exe"
        set "SWIFT_URL=https://download.swift.org/swift-6.2.4-release/windows10/swift-6.2.4-RELEASE/swift-6.2.4-RELEASE-windows10.exe"
        powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%SWIFT_URL%' -OutFile '%SWIFT_INSTALLER%' -UseBasicParsing } catch { Write-Host $_.Exception.Message; exit 1 }"
        if exist "%SWIFT_INSTALLER%" (
            echo Running Swift installer (may require confirmation)...
            start /wait "" "%SWIFT_INSTALLER%" /passive
            del /q "%SWIFT_INSTALLER%" 2>nul
        ) else (
            echo Download failed. Please install Swift manually from https://swift.org/install/windows/
            popd
            pause
            exit /b 1
        )
    )
    set "SWIFT_JUST_INSTALLED=1"
)

rem Build Swift module (use PowerShell with refreshed PATH if we just installed)
if "%SWIFT_JUST_INSTALLED%"=="1" (
    echo Building Swift md_ingest with refreshed PATH...
    powershell -NoProfile -Command "Set-Location -LiteralPath '%CD%'; $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User'); & swift build -c release --package-path 'swift-md-ingest'; exit $LASTEXITCODE"
) else (
    swift build -c release --package-path "swift-md-ingest"
)

if %errorlevel% neq 0 (
    echo.
    echo Swift md_ingest build failed.
    if "%SWIFT_JUST_INSTALLED%"=="1" (
        echo If Swift was just installed, close this window, open a new one, and run build_app.bat again.
    )
    popd
    pause
    exit /b 1
)

copy /Y "swift-md-ingest\.build\release\swift-md-ingest.exe" "bin\swift-md-ingest.exe" >nul 2>&1
if %errorlevel% neq 0 (
    rem Try non-.exe name (e.g. on non-Windows Swift toolchains)
    copy /Y "swift-md-ingest\.build\release\swift-md-ingest" "bin\swift-md-ingest" >nul 2>&1
)

popd

echo.
echo Build completed successfully!
echo The React app is ready in the dist/ folder, Swift md_ingest binary in bin/.
echo.

