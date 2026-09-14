#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Start ChironAI at Windows logon so Open WebUI has a proxy after a full boot.

.DESCRIPTION
  Needed only for Shutdown (S5) + WoL. Sleep (S3) keeps processes in RAM and
  does not need this task. Docker Desktop still needs "Start when you sign in".
#>
[CmdletBinding()]
param(
    [switch]$Disable
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = 'ChironAI WebUI logon'
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$StartBat = Join-Path $RepoRoot 'start_webui.bat'

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

if (-not (Test-PhoneHostScriptEnabled 'setup-logon-autostart')) {
    Write-Host 'SCRIPT_DISABLED setup-logon-autostart'
    exit 20
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Disable) {
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'."
    } else {
        Write-Host "Task '$TaskName' was not registered."
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $StartBat)) {
    throw "start_webui.bat not found at $StartBat"
}

$action = New-ScheduledTaskAction -Execute $StartBat -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

if ($existing) {
    Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
    Write-Host "Updated scheduled task '$TaskName'."
} else {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
    Write-Host "Registered scheduled task '$TaskName'."
}

Write-Host "Runs $StartBat at logon for $env:USERNAME."
Write-Host 'Docker Desktop: enable "Start Docker Desktop when you sign in".'
Write-Host 'Windows auto-login is a separate OS setting if you wake from Shutdown without typing a password.'
