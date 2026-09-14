#Requires -Version 5.1
<#
.SYNOPSIS
  Limit Sunshine/Moonlight inbound to home LAN and Keenetic WireGuard.

.DESCRIPTION
  Replaces the installer Allow-Any Sunshine rules with RemoteAddress
  192.168.50.0/24 (Ethernet) and 10.6.0.0/24 (router WireGuard).
  PrivadoVPN is not in that list. Does not stop the Sunshine service.
#>
[CmdletBinding()]
param(
    [switch]$Elevated,
    [string[]]$RemoteCidrs = @('192.168.50.0/24', '10.6.0.0/24')
)

$ErrorActionPreference = 'Stop'
$RulePrefix = 'ChironAI Sunshine LAN'
$Exe = Join-Path $env:ProgramFiles 'Sunshine\sunshine.exe'

if ($RemoteCidrs.Count -eq 1 -and $RemoteCidrs[0] -match ',') {
    $RemoteCidrs = @($RemoteCidrs[0].Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Set-SunshineLanFirewall {
    if (-not (Test-Path -LiteralPath $Exe)) {
        throw "sunshine.exe not found: $Exe"
    }

    Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object {
        $_.DisplayName -eq 'Sunshine' -or
        $_.DisplayName -like "$RulePrefix*" -or
        $_.Name -like 'ChironAI-Sunshine-LAN*'
    } | Remove-NetFirewallRule -ErrorAction SilentlyContinue

    New-NetFirewallRule -Name 'ChironAI-Sunshine-LAN-TCP' `
        -DisplayName "$RulePrefix TCP" `
        -Direction Inbound -Action Allow -Enabled True `
        -Profile Any `
        -Protocol TCP `
        -RemoteAddress $RemoteCidrs `
        -Program $Exe | Out-Null

    New-NetFirewallRule -Name 'ChironAI-Sunshine-LAN-UDP' `
        -DisplayName "$RulePrefix UDP" `
        -Direction Inbound -Action Allow -Enabled True `
        -Profile Any `
        -Protocol UDP `
        -RemoteAddress $RemoteCidrs `
        -Program $Exe | Out-Null

    Write-Host "Sunshine inbound limited to $($RemoteCidrs -join ', ')."
}

if (-not $Elevated -and -not (Test-IsAdministrator)) {
    Write-Host 'Requesting Administrator to replace Sunshine firewall rules...'
    $cidrs = ($RemoteCidrs | ForEach-Object { $_.ToString() }) -join ','
    $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $PSCommandPath,
        '-Elevated',
        '-RemoteCidrs', $cidrs
    )
    if ($proc.ExitCode -ne 0) {
        throw "Elevated repair failed with exit code $($proc.ExitCode)"
    }
    exit 0
}

if (-not (Test-IsAdministrator)) {
    throw 'Administrator is required.'
}

Set-SunshineLanFirewall
exit 0
