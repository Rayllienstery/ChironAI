#Requires -Version 5.1
<#
.SYNOPSIS
  Allow RustDesk from Keenetic WireGuard as well as Ethernet LAN.
#>
[CmdletBinding()]
param(
    [switch]$Elevated,
    [string[]]$RemoteCidrs = @('192.168.50.0/24', '10.6.0.0/24')
)

$ErrorActionPreference = 'Stop'

if ($RemoteCidrs.Count -eq 1 -and $RemoteCidrs[0] -match ',') {
    $RemoteCidrs = @($RemoteCidrs[0].Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Set-WhitelistInToml([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $wanted = ($RemoteCidrs -join ',')
    $updated = [regex]::Replace($raw, "(?m)^whitelist = '.*'$", "whitelist = '$wanted'")
    if ($updated -eq $raw) { return }
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $updated, $utf8)
    Write-Host "Updated whitelist in $Path"
}

if (-not $Elevated -and -not (Test-IsAdministrator)) {
    $cidrs = ($RemoteCidrs | ForEach-Object { $_.ToString() }) -join ','
    Write-Host 'Requesting Administrator for RustDesk firewall + service restart...'
    $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath,
        '-Elevated', '-RemoteCidrs', $cidrs
    )
    if ($proc.ExitCode -ne 0) {
        throw "Elevated repair failed with exit code $($proc.ExitCode)"
    }
    exit 0
}

if (-not (Test-IsAdministrator)) {
    throw 'Administrator is required.'
}

Set-WhitelistInToml (Join-Path $env:APPDATA 'RustDesk\config\RustDesk2.toml')
Set-WhitelistInToml 'C:\Windows\System32\config\systemprofile\AppData\Roaming\RustDesk\config\RustDesk2.toml'

Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object {
    $_.DisplayName -like 'ChironAI RustDesk LAN*'
} | ForEach-Object {
    Set-NetFirewallRule -Name $_.Name -RemoteAddress $RemoteCidrs
    Write-Host "Firewall $($_.DisplayName) -> $($RemoteCidrs -join ', ')"
}

$svc = Get-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
if ($svc) {
    Restart-Service -Name 'RustDesk' -Force
    Write-Host 'RustDesk service restarted so the whitelist loads.'
}

Write-Host "Connect to 192.168.50.115:21118 from LAN or Keenetic WG. Not the public ID."
exit 0
