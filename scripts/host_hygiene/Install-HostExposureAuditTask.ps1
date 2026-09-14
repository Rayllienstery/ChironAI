#Requires -Version 5.1
<#
.SYNOPSIS
  Register or remove the periodic host exposure audit task.
#>
[CmdletBinding()]
param(
    [switch]$Disable,
    [int]$EveryHours = 6
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = 'ChironAI Host Exposure Audit'
$Audit = Join-Path $ScriptDir 'Invoke-HostExposureAudit.ps1'

if (-not (Test-Path -LiteralPath $Audit)) {
    throw "Audit script not found: $Audit"
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

if ($EveryHours -lt 1) {
    throw 'EveryHours must be >= 1'
}

$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Audit`" -Notify"
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg -WorkingDirectory $ScriptDir
$startAt = (Get-Date).AddMinutes(3)
$repeat = New-ScheduledTaskTrigger -Once -At $startAt -RepetitionInterval (New-TimeSpan -Hours $EveryHours) -RepetitionDuration (New-TimeSpan -Days 3650)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

if ($existing) {
    Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($repeat, $logon) -Settings $settings -Principal $principal | Out-Null
    Write-Host "Updated scheduled task '$TaskName'."
} else {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($repeat, $logon) -Settings $settings -Principal $principal | Out-Null
    Write-Host "Registered scheduled task '$TaskName'."
}

Write-Host "Runs every $EveryHours hours and at logon for $env:USERNAME."
Write-Host "First repeat fire around $($startAt.ToString('HH:mm'))."
Write-Host 'Reports: %LOCALAPPDATA%\ChironAI\host_hygiene\'
Write-Host 'Toasts only on high/critical findings.'
