<#
.SYNOPSIS
  Sunshine stream start/stop bridge to switch_display.ahk.

.DESCRIPTION
  Prep from Sunshine cannot reliably call DisplaySwitch / ChangeDisplaySettings
  (EnumDisplaySettingsW fails in that process tree). Instead we drop a request
  file that the interactive AutoHotkey script polls and applies.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('start', 'stop')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StateDir = Join-Path $ScriptDir 'state'
$StateFile = Join-Path $StateDir 'hd-stream.json'
$LogFile = Join-Path $StateDir 'on-stream-display.log'
$RequestFile = Join-Path $StateDir 'display-request.txt'
$AckFile = Join-Path $StateDir 'display-ack.txt'
$AhkScript = 'C:\Users\Raylee\Documents\switch_display.ahk'
$AhkExe = 'C:\Program Files\AutoHotkey\AutoHotkeyU64.exe'

function Write-Log([string]$Message) {
    if (-not (Test-Path -LiteralPath $StateDir)) {
        New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    }
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    Write-Output $line
}

function Test-IsHdClient([int]$Width, [int]$Height) {
    if ($Width -le 0 -or $Height -le 0) { return $false }
    $max = [Math]::Max($Width, $Height)
    $min = [Math]::Min($Width, $Height)
    return ($max -le 1920 -and $min -le 1080)
}

function Get-ClientSize {
    $w = 0
    $h = 0
    [void][int]::TryParse([Environment]::GetEnvironmentVariable('SUNSHINE_CLIENT_WIDTH'), [ref]$w)
    [void][int]::TryParse([Environment]::GetEnvironmentVariable('SUNSHINE_CLIENT_HEIGHT'), [ref]$h)
    return @{ Width = $w; Height = $h }
}

function Save-State([hashtable]$State) {
    if (-not (Test-Path -LiteralPath $StateDir)) {
        New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    }
    ($State | ConvertTo-Json -Compress) | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Read-State {
    if (-not (Test-Path -LiteralPath $StateFile)) { return $null }
    try {
        return Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Clear-State {
    if (Test-Path -LiteralPath $StateFile) {
        Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
    }
}

function Ensure-AhkRunning {
    $wanted = $AhkScript.ToLowerInvariant()
    $existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^AutoHotkey' -and
            $_.CommandLine -and
            $_.CommandLine.ToLowerInvariant().Contains($wanted)
        }
    if ($existing) { return $true }

    if (-not (Test-Path -LiteralPath $AhkExe)) {
        Write-Log "ERROR: AutoHotkey not found at $AhkExe"
        return $false
    }
    if (-not (Test-Path -LiteralPath $AhkScript)) {
        Write-Log "ERROR: switch_display.ahk not found at $AhkScript"
        return $false
    }

    # Prefer reloading our script over a stale AHK instance without the bridge timer.
    Get-Process AutoHotkey* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 400
    Start-Process -FilePath $AhkExe -ArgumentList "`"$AhkScript`"" -WindowStyle Hidden
    Start-Sleep -Milliseconds 1000
    $existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^AutoHotkey' -and
            $_.CommandLine -and
            $_.CommandLine.ToLowerInvariant().Contains($wanted)
        }
    if (-not $existing) {
        Write-Log 'ERROR: failed to start switch_display.ahk'
        return $false
    }
    Write-Log 'started switch_display.ahk'
    return $true
}

function Send-DisplayRequest([string]$Request, [int]$TimeoutSec = 15) {
    if (-not (Test-Path -LiteralPath $StateDir)) {
        New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    }
    if (-not (Ensure-AhkRunning)) {
        throw 'AutoHotkey bridge is not available'
    }
    Remove-Item -LiteralPath $AckFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $RequestFile -Force -ErrorAction SilentlyContinue
    Set-Content -LiteralPath $RequestFile -Value $Request -Encoding ASCII -NoNewline
    Write-Log "request=$Request written"

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $AckFile) {
            $ack = (Get-Content -LiteralPath $AckFile -Raw -ErrorAction SilentlyContinue).Trim()
            Remove-Item -LiteralPath $AckFile -Force -ErrorAction SilentlyContinue
            Write-Log "ack=$ack"
            if ($ack -ne 'ok') {
                throw "AHK ack failed: $ack"
            }
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "AHK ack timeout after ${TimeoutSec}s (is switch_display.ahk running?)"
}

try {
    if ($Action -eq 'start') {
        $client = Get-ClientSize
        Write-Log ("start client={0}x{1}" -f $client.Width, $client.Height)
        if (-not (Test-IsHdClient $client.Width $client.Height)) {
            Write-Log 'not HD - leave display alone'
            Clear-State
            exit 0
        }
        # Arm restore even before AHK finishes, so undo still runs if stream ends early.
        Save-State @{
            switched = $true
            clientWidth = $client.Width
            clientHeight = $client.Height
            at = (Get-Date).ToString('o')
        }
        Send-DisplayRequest -Request 'hd' -TimeoutSec 20
        Write-Log 'HD -> AHK dongle + Switch mode'
    }
    else {
        $state = Read-State
        if (-not $state -or -not $state.switched) {
            Write-Log 'stop - no HD switch was armed, skip'
            Clear-State
            exit 0
        }
        Write-Log 'stop - restore via AHK'
        Send-DisplayRequest -Request 'restore' -TimeoutSec 20
        Clear-State
        Write-Log 'restored real monitor'
    }
    exit 0
}
catch {
    Write-Log ("ERROR: {0}" -f $_.Exception.Message)
    # Never abort the Moonlight stream because of display prep.
    exit 0
}
