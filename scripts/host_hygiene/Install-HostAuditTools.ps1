#Requires -Version 5.1
<#
.SYNOPSIS
  Install optional open-source tools used by Invoke-HostExposureAudit.ps1 -Deep.

.DESCRIPTION
  - HardeningKitty (CIS-style Windows audit) into %LOCALAPPDATA%\ChironAI\host_hygiene\tools\HardeningKitty
  - Trivy via winget when available (Docker image CVE scan)
#>
[CmdletBinding()]
param(
    [switch]$SkipTrivy,
    [switch]$SkipHardeningKitty
)

$ErrorActionPreference = 'Stop'
$toolsRoot = Join-Path $env:LOCALAPPDATA 'ChironAI\host_hygiene\tools'
New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null

if (-not $SkipHardeningKitty) {
    $hkDir = Join-Path $toolsRoot 'HardeningKitty'
    $zipPath = Join-Path $env:TEMP 'HardeningKitty.zip'
    $url = 'https://github.com/scipag/HardeningKitty/archive/refs/heads/master.zip'
    Write-Host "Downloading HardeningKitty..."
    Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
    if (Test-Path -LiteralPath $hkDir) {
        Remove-Item -LiteralPath $hkDir -Recurse -Force
    }
    $extract = Join-Path $env:TEMP 'HardeningKitty-extract'
    if (Test-Path -LiteralPath $extract) {
        Remove-Item -LiteralPath $extract -Recurse -Force
    }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extract -Force
    $inner = Get-ChildItem -Path $extract -Directory | Select-Object -First 1
    if (-not $inner) { throw 'HardeningKitty zip layout unexpected' }
    Move-Item -LiteralPath $inner.FullName -Destination $hkDir
    Remove-Item -LiteralPath $extract -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    Unblock-File -Path (Join-Path $hkDir '*') -ErrorAction SilentlyContinue
    Write-Host "HardeningKitty -> $hkDir"
}

if (-not $SkipTrivy) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host 'Installing Trivy via winget (AquaSecurity.Trivy)...'
        & winget install --id AquaSecurity.Trivy -e --accept-package-agreements --accept-source-agreements
    } else {
        Write-Warning 'winget not found. Install Trivy manually: https://github.com/aquasecurity/trivy/releases'
    }
}

Write-Host ''
Write-Host 'Done. Run a deep audit:'
Write-Host '  powershell -NoProfile -ExecutionPolicy Bypass -File .\Invoke-HostExposureAudit.ps1 -Deep'
