#Requires -Version 5.1
<#
.SYNOPSIS
  Stop SMB / NetBIOS from leaking onto PrivadoVPN. Keep LAN shares.

.DESCRIPTION
  Unbinds File and Printer Sharing from PrivadoVPN adapters, disables NetBIOS
  on those adapters, turns off Public-profile Restrictive SMB-In, and adds
  explicit Block rules for 137/138/139/445 on the Public profile (VPN).

  Ethernet stays Private. ComfyUI SMB LAN allowlist is left in place.
#>
[CmdletBinding()]
param(
    [switch]$Elevated
)

$ErrorActionPreference = 'Stop'

$RulePrefix = 'ChironAI Block SMB Public'
$AdapterMatch = 'PrivadoVPN'
$LanCidrs = @('192.168.50.0/24', '10.6.0.0/24', '192.168.1.0/24')

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-VpnAdapters {
    @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*$AdapterMatch*" })
}

function Disable-VpnFileSharing {
    foreach ($adapter in (Get-VpnAdapters)) {
        $binding = Get-NetAdapterBinding -Name $adapter.Name -ComponentID ms_server -ErrorAction SilentlyContinue
        if ($binding -and $binding.Enabled) {
            Disable-NetAdapterBinding -Name $adapter.Name -ComponentID ms_server -Confirm:$false
            Write-Host "Disabled File and Printer Sharing on '$($adapter.Name)'."
        } else {
            Write-Host "File and Printer Sharing already off on '$($adapter.Name)'."
        }
    }
}

function Disable-VpnNetbios {
    foreach ($adapter in (Get-VpnAdapters)) {
        $cfg = Get-CimInstance Win32_NetworkAdapterConfiguration -ErrorAction SilentlyContinue |
            Where-Object { $_.InterfaceIndex -eq $adapter.ifIndex }
        if (-not $cfg) {
            Write-Warning "No TCP/IP config for '$($adapter.Name)'; skipped NetBIOS."
            continue
        }
        $result = Invoke-CimMethod -InputObject $cfg -MethodName SetTcpipNetbios -Arguments @{ TcpipNetbiosOptions = 2 }
        if ($result.ReturnValue -eq 0) {
            Write-Host "Disabled NetBIOS on '$($adapter.Name)'."
        } else {
            Write-Warning "SetTcpipNetbios returned $($result.ReturnValue) on '$($adapter.Name)'."
        }
    }
}

function Set-PublicSmbFirewall {
    Get-NetFirewallRule -DisplayName 'File and Printer Sharing (Restrictive) (SMB-In)' -ErrorAction SilentlyContinue |
        Where-Object { $_.Profile -match 'Public' } |
        ForEach-Object {
            if ($_.Enabled -eq 'True') {
                Disable-NetFirewallRule -Name $_.Name
                Write-Host "Disabled '$($_.DisplayName)' on Public."
            }
        }

    Get-NetFirewallRule -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like "$RulePrefix*" -or $_.Name -like 'ChironAI-Block-SMB-Public*' } |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue

    New-NetFirewallRule -Name 'ChironAI-Block-SMB-Public-TCP' `
        -DisplayName "$RulePrefix TCP" `
        -Direction Inbound -Action Block -Enabled True `
        -Profile Public `
        -Protocol TCP -LocalPort 139,445 | Out-Null

    New-NetFirewallRule -Name 'ChironAI-Block-SMB-Public-UDP' `
        -DisplayName "$RulePrefix UDP" `
        -Direction Inbound -Action Block -Enabled True `
        -Profile Public `
        -Protocol UDP -LocalPort 137,138 | Out-Null

    Write-Host "Public inbound 137/138/139/445 is blocked. LAN CIDRs unchanged: $($LanCidrs -join ', ')."
}

function Show-SmbListen {
    Write-Host ''
    Write-Host 'SMB listeners after repair:'
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 139,445 } |
        Select-Object LocalAddress, LocalPort |
        Format-Table -AutoSize
    Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 137,138 } |
        Select-Object LocalAddress, LocalPort |
        Format-Table -AutoSize
}

if (-not $Elevated -and -not (Test-IsAdministrator)) {
    Write-Host 'Requesting Administrator to unbind SMB from PrivadoVPN...'
    $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $PSCommandPath,
        '-Elevated'
    )
    if ($proc.ExitCode -ne 0) {
        throw "Elevated repair failed with exit code $($proc.ExitCode)"
    }
    Show-SmbListen
    exit 0
}

if (-not (Test-IsAdministrator)) {
    throw 'Administrator is required.'
}

Disable-VpnFileSharing
Disable-VpnNetbios
Set-PublicSmbFirewall
Show-SmbListen

$vpnSmb = @(
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 139,445 -and $_.LocalAddress -like '100.*' }
    Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 137,138 -and $_.LocalAddress -like '100.*' }
)
if ($vpnSmb.Count -gt 0) {
    Write-Warning 'VPN still has SMB/NetBIOS listeners. Firewall Public block is in place; a reconnect may be needed to drop the binds.'
    exit 2
}

Write-Host ''
Write-Host 'SMB is off the VPN adapters. LAN shares on Ethernet should still work.'
exit 0
