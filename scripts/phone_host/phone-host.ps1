<#
.SYNOPSIS
  Compact ChironAI phone-host actions for iPhone Shortcuts over SSH.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('status', 'sleep', 'wake-help')]
    [string]$Action = 'status',
    [int]$Port = 0,
    [switch]$Json
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

if (-not (Test-PhoneHostScriptEnabled 'phone-host')) {
    Write-Output 'SCRIPT_DISABLED phone-host'
    exit 20
}

function Get-HostPort {
    if ($Port -gt 0) { return $Port }
    foreach ($name in @('CHIRONAI_PHONE_STATUS_PORT', 'CHIRONAI_ACTIVE_SERVER_PORT', 'SERVER_PORT')) {
        $raw = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($raw)) {
            $parsed = 0
            if ([int]::TryParse($raw, [ref]$parsed) -and $parsed -ge 1 -and $parsed -le 65535) {
                return $parsed
            }
        }
    }
    return 8080
}

function Invoke-LocalJson([string]$Url, [int]$TimeoutSec) {
    try {
        return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec $TimeoutSec
    } catch {
        return $null
    }
}

function Write-Payload($Payload, [string]$FallbackMessage) {
    if ($Json) {
        $Payload | ConvertTo-Json -Compress
        return
    }
    if ($Payload -and $Payload.message) {
        Write-Output $Payload.message
        return
    }
    Write-Output $FallbackMessage
}

function Get-StatusPayload {
    $hostPort = Get-HostPort
    $live = Invoke-LocalJson "http://127.0.0.1:$hostPort/live" 2
    if ($null -eq $live) {
        return [pscustomobject]@{
            host        = 'awake'
            chiron      = 'starting'
            generating  = $false
            kind        = $null
            detail      = $null
            gpu_pct     = $null
            active_traces = 0
            status      = 'starting'
            message     = 'PC awake, Chiron still starting'
        }
    }
    $status = Invoke-LocalJson "http://127.0.0.1:$hostPort/api/webui/host/phone-status" 5
    if ($null -eq $status) {
        return [pscustomobject]@{
            host       = 'awake'
            chiron     = 'starting'
            generating = $false
            message    = 'PC awake, Chiron still starting'
        }
    }
    return $status
}

switch ($Action) {
    'wake-help' {
        Get-Content -LiteralPath (Join-Path $ScriptDir 'router-wake.examples.txt') -Raw
    }
    'status' {
        $payload = Get-StatusPayload
        Write-Payload $payload 'PC awake'
        if ($payload.generating) { exit 10 }
        if ($payload.chiron -eq 'starting') { exit 2 }
        exit 0
    }
    'sleep' {
        $payload = Get-StatusPayload
        if ($payload.generating) {
            $msg = if ($payload.detail) { "SLEEP_BLOCKED generating: $($payload.detail)" } else { 'SLEEP_BLOCKED generating' }
            Write-Output $msg
            exit 10
        }
        rundll32.exe powrprof.dll,SetSuspendState 0,1,0
        Write-Output 'SLEEP_OK'
        exit 0
    }
}
