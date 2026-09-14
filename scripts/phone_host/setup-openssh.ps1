#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Install OpenSSH Server and a dedicated iPhone key for Chiron phone-host Shortcuts.
#>
[CmdletBinding()]
param()

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

if (-not (Test-PhoneHostScriptEnabled 'setup-openssh')) {
    Write-Host 'SCRIPT_DISABLED setup-openssh'
    exit 20
}

$sshDir = Join-Path $env:USERPROFILE '.ssh'
$keyPath = Join-Path $sshDir 'chiron-iphone_ed25519'
$authKeys = Join-Path $sshDir 'authorized_keys'

Write-Host 'Installing OpenSSH Server...'
$capability = Get-WindowsCapability -Online | Where-Object { $_.Name -like 'OpenSSH.Server*' } | Select-Object -First 1
if (-not $capability) {
    throw 'OpenSSH.Server capability was not found on this Windows image.'
}
if ($capability.State -ne 'Installed') {
    Add-WindowsCapability -Online -Name $capability.Name | Out-Null
}

Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
Get-Service sshd | Format-List Name, Status, StartType

$fw = Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue
if ($fw) {
    Set-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -Profile Private,Domain -Enabled True
}

New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
if (-not (Test-Path -LiteralPath $keyPath)) {
    & "$env:WINDIR\System32\OpenSSH\ssh-keygen.exe" -t ed25519 -f $keyPath -N ([string]::Empty) -C 'chiron-iphone'
}

$pub = Get-Content -LiteralPath "$keyPath.pub" -Raw
if (-not (Test-Path -LiteralPath $authKeys) -or -not (Select-String -LiteralPath $authKeys -Pattern [regex]::Escape($pub.Trim()) -Quiet)) {
    Add-Content -LiteralPath $authKeys -Value $pub.Trim() -Encoding ascii
}

icacls $authKeys /inheritance:r | Out-Null
icacls $authKeys /grant:r "$($env:USERNAME):(R)" | Out-Null

Write-Host ''
Write-Host "Private key (copy this file to the iPhone Files app): $keyPath"
Write-Host "Public key installed into: $authKeys"
Write-Host 'Shortcut SSH script: C:\Users\Raylee\AI\scripts\phone_host\phone-host.cmd status'
Write-Host 'See docs/PHONE_HOST.md and scripts/phone_host/IOS_SHORTCUT.md'
