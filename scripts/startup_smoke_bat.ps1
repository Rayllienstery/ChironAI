#!/usr/bin/env pwsh
# Windows startup smoke (Phase 5) — build CoreUI and verify the WebUI server is ready.
# This script intentionally does NOT stop a running application. If the server is
# already up, it is reused. If it is not responding, the script starts a new instance
# and leaves it running.
#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path -Path $root -ChildPath "CoreModules" | Join-Path -ChildPath "CoreUI"
$stdoutLog = Join-Path -Path $root -ChildPath "tmp" | Join-Path -ChildPath "build_and_run_smoke.log"
$stderrLog = Join-Path -Path $root -ChildPath "tmp" | Join-Path -ChildPath "build_and_run_smoke.err.log"
$healthRetries = 45
$healthDelaySec = 2

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

function Get-ServerUrl {
    $env:PYTHONPATH = "$root;$root\Core;$root\Core\modules\webui_backend;" + $env:PYTHONPATH
    $url = & python -m webui_backend.print_server_url 2>$null | Select-Object -Last 1
    if (-not $url) {
        $url = "http://127.0.0.1:8080/webui"
    }
    return $url
}

function Get-HealthUrl {
    param([string]$Url)
    $baseUrl = ($Url -replace '/webui$', '') -replace '://localhost:', '://127.0.0.1:'
    return "$baseUrl/api/webui/version"
}

function Test-ServerReady {
    param([string]$HealthUrl)
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Invoke-CoreUIBuild {
    Write-Step "CoreUI build"
    if (-not (Test-Path -LiteralPath $frontend)) {
        throw "Front-end directory not found: $frontend"
    }
    Push-Location -LiteralPath $frontend
    try {
        $env:CHIRONAI_FORCE_COREUI_BUILD = "0"
        & npm.cmd run build | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) {
            throw "CoreUI build failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

function Start-WebUIServer {
    Write-Step "Starting WebUI server"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $stdoutLog) | Out-Null
    $env:PYTHONPATH = "$root;$root\Core;$root\Core\modules\webui_backend;" + $env:PYTHONPATH

    # Clear any previous listeners on known ports so the new server can bind.
    & python -m webui_backend.kill_listeners_on_config_port | ForEach-Object { Write-Host $_ }

    $process = Start-Process -FilePath "python" `
        -ArgumentList "-m", "webui_backend.rag_proxy" `
        -WorkingDirectory $root `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru `
        -WindowStyle Hidden

    return $process
}

function Wait-ForServerReady {
    param([string]$Url, [System.Diagnostics.Process]$Process)
    Write-Step "Waiting for server at $Url"
    $versionUrl = Get-HealthUrl -Url $Url
    for ($i = 0; $i -lt $healthRetries; $i++) {
        if ($Process.HasExited) {
            throw "Server process exited early with code $($Process.ExitCode). See $stderrLog"
        }
        if (Test-ServerReady -HealthUrl $versionUrl) {
            Write-Step "Server ready"
            return
        }
        Write-Host "  health poll attempt $($i + 1)/$healthRetries ..."
        Start-Sleep -Seconds $healthDelaySec
    }
    throw "Server did not become ready within $($healthRetries * $healthDelaySec) seconds. See $stdoutLog and $stderrLog"
}

Invoke-CoreUIBuild
$serverUrl = Get-ServerUrl
$healthUrl = Get-HealthUrl -Url $serverUrl

if (Test-ServerReady -HealthUrl $healthUrl) {
    Write-Step "Server already running at $serverUrl"
    Write-Host ""
    Write-Host "PASS: startup_smoke_bat (reusing existing server at $serverUrl)"
    exit 0
}

$serverProcess = Start-WebUIServer
Wait-ForServerReady -Url $serverUrl -Process $serverProcess

Write-Host ""
Write-Host "PASS: startup_smoke_bat (server left running at $serverUrl)"
