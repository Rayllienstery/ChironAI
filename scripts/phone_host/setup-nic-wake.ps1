#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Enable Wake-on-LAN so this PC can wake from S3/S5 on a magic packet
  or on a directed TCP packet (Open WebUI from the iPhone).

.DESCRIPTION
  Targets the Realtek Ethernet used by phone-host (MAC 74-56-3C-36-A3-76)
  unless -Mac is passed. Disables Energy-Efficient Ethernet / Green Ethernet
  because those modes drop magic packets on Realtek NICs.

  BIOS Wake-on-LAN / PME still needs a one-time human check.
#>
[CmdletBinding()]
param(
    [string]$Mac = '74-56-3C-36-A3-76',
    [switch]$SkipPatternWake
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-PhoneHostScriptEnabled([string]$ScriptId) {
    $file = Join-Path $ScriptDir 'enabled.json'
    if (-not (Test-Path -LiteralPath $file)) { return $true }
    try {
        $map = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
    } catch {
        return $true
    }
    $prop = $map.PSObject.Properties[$ScriptId]
    if ($null -eq $prop) { return $true }
    return [bool]$prop.Value
}

if (-not (Test-PhoneHostScriptEnabled 'setup-nic-wake')) {
    Write-Host 'SCRIPT_DISABLED setup-nic-wake'
    exit 20
}

function ConvertTo-MacCanonical([string]$Value) {
    $hex = ($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant()
    if ($hex.Length -ne 12) {
        throw "MAC must be 6 bytes, got: $Value"
    }
    return (($hex -split '(.{2})' | Where-Object { $_ }) -join '-').ToUpperInvariant()
}

function Set-AdapterAdvancedFlag {
    param(
        [string]$AdapterName,
        [string[]]$DisplayNameMatch,
        [string]$Wanted,
        [string]$Kind
    )
    $props = Get-NetAdapterAdvancedProperty -Name $AdapterName -ErrorAction SilentlyContinue
    foreach ($prop in $props) {
        $display = [string]$prop.DisplayName
        $hit = $false
        foreach ($pattern in $DisplayNameMatch) {
            if ($display -like $pattern) { $hit = $true; break }
        }
        if (-not $hit) { continue }
        $current = [string]$prop.DisplayValue
        if ($current -eq $Wanted) {
            Write-Host "  [$Kind] $display = $current (already)"
            return $true
        }
        Set-NetAdapterAdvancedProperty -Name $AdapterName -DisplayName $display -DisplayValue $Wanted
        Write-Host "  [$Kind] $display : $current -> $Wanted"
        return $true
    }
    Write-Host "  [$Kind] no matching advanced property ($($DisplayNameMatch -join ', '))"
    return $false
}

$wantedMac = ConvertTo-MacCanonical $Mac
$adapter = Get-NetAdapter -Physical | Where-Object {
    (ConvertTo-MacCanonical $_.MacAddress) -eq $wantedMac
} | Select-Object -First 1

if (-not $adapter) {
    $adapter = Get-NetAdapter -Physical | Where-Object {
        $_.Status -eq 'Up' -and $_.MediaType -like '*802.3*'
    } | Select-Object -First 1
}

if (-not $adapter) {
    throw "No Ethernet adapter found for MAC $wantedMac."
}

Write-Host "Adapter: $($adapter.Name)  $($adapter.InterfaceDescription)"
Write-Host "MAC:     $($adapter.MacAddress)  Status: $($adapter.Status)"
Write-Host ""

Set-NetAdapterPowerManagement -Name $adapter.Name -WakeOnMagicPacket Enabled
if ($SkipPatternWake) {
    Write-Host 'WakeOnPattern: skipped (-SkipPatternWake). Magic packet only.'
} else {
    try {
        Set-NetAdapterPowerManagement -Name $adapter.Name -WakeOnPattern Enabled
    } catch {
        Write-Host "WakeOnPattern: $($_.Exception.Message)"
    }
}

$pnp = Get-PnpDeviceProperty -InstanceId $adapter.PnPDeviceID -KeyName 'DEVPKEY_Device_WakeEnabled' -ErrorAction SilentlyContinue
if ($pnp) {
    Write-Host "PnP wake enabled: $($pnp.Data)"
}

try {
    powercfg /deviceenablewake $adapter.InterfaceDescription | Out-Null
    Write-Host "powercfg wake: enabled for '$($adapter.InterfaceDescription)'"
} catch {
    Write-Host "powercfg wake: $($_.Exception.Message)"
}

Write-Host ''
Write-Host 'Advanced NIC properties:'
Set-AdapterAdvancedFlag -AdapterName $adapter.Name -DisplayNameMatch @('*Wake on Magic*', '*Magic Packet*') -Wanted 'Enabled' -Kind 'wol' | Out-Null
if (-not $SkipPatternWake) {
    Set-AdapterAdvancedFlag -AdapterName $adapter.Name -DisplayNameMatch @('*Wake on Pattern*', '*pattern match*') -Wanted 'Enabled' -Kind 'pattern' | Out-Null
}
Set-AdapterAdvancedFlag -AdapterName $adapter.Name -DisplayNameMatch @('*Shutdown Wake*') -Wanted 'Enabled' -Kind 's5' | Out-Null
Set-AdapterAdvancedFlag -AdapterName $adapter.Name -DisplayNameMatch @('*Energy Efficient Ethernet*', '*EEE*') -Wanted 'Disabled' -Kind 'eee' | Out-Null
Set-AdapterAdvancedFlag -AdapterName $adapter.Name -DisplayNameMatch @('*Green Ethernet*') -Wanted 'Disabled' -Kind 'green' | Out-Null

Write-Host ''
Write-Host 'Power management snapshot:'
Get-NetAdapterPowerManagement -Name $adapter.Name |
    Select-Object Name, WakeOnMagicPacket, WakeOnPattern, AllowComputerToTurnOffDevice |
    Format-List

Write-Host 'Still required (human):'
Write-Host '  1. BIOS/UEFI: Wake-on-LAN / PME / Power on by PCI-E = Enabled'
Write-Host '  2. Router: DHCP reservation + static ARP for this MAC -> 192.168.50.115'
Write-Host '  3. Prefer Sleep (S3), not Shutdown. Open WebUI stays in RAM after WoL.'
Write-Host '  4. iPhone Shortcut "Chiron Chat" or the router door on :9377'
Write-Host ''
Write-Host 'See docs/PHONE_HOST.md'
