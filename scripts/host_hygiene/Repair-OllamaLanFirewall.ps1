#Requires -Version 5.1
<#
.SYNOPSIS
  Limit inbound Ollama (TCP 11434) to Ethernet LAN and Keenetic WireGuard.

.DESCRIPTION
  Replaces Public/Any ollama.exe rules with RemoteAddress 192.168.50.0/24 +
  10.6.0.0/24. Port 11434 is allowed that way for both native ollama.exe and
  Docker publish. Public profile 11434 is blocked so PrivadoVPN cannot sneak
  through a Docker Allow-Any. Loopback (ChironAI) is unchanged.
#>
[CmdletBinding()]
param(
    [switch]$Elevated,
    [string[]]$RemoteCidrs = @('192.168.50.0/24', '10.6.0.0/24'),
    [int]$ListenPort = 11434
)

$ErrorActionPreference = 'Stop'
$RulePrefix = 'ChironAI Ollama LAN'
$BlockPrefix = 'ChironAI Block Ollama Public'
$HostBind = '0.0.0.0:11434'
$ExeCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'),
    (Join-Path $env:ProgramFiles 'Ollama\ollama.exe')
)

if ($RemoteCidrs.Count -eq 1 -and $RemoteCidrs[0] -match ',') {
    $RemoteCidrs = @($RemoteCidrs[0].Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not $Elevated -and -not (Test-IsAdministrator)) {
    Write-Host 'Requesting Administrator to restrict Ollama inbound firewall...'
    $cidrs = ($RemoteCidrs | ForEach-Object { $_.ToString() }) -join ','
    $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath,
        '-Elevated', '-RemoteCidrs', $cidrs, '-ListenPort', $ListenPort
    )
    if ($proc.ExitCode -ne 0) {
        throw "Elevated repair failed with exit code $($proc.ExitCode)"
    }
    exit 0
}

if (-not (Test-IsAdministrator)) {
    throw 'Administrator is required.'
}

$inbound = @(Get-NetFirewallRule -Direction Inbound -Action Allow -ErrorAction SilentlyContinue)
$programs = New-Object 'System.Collections.Generic.List[string]'
$removed = 0
foreach ($rule in $inbound) {
    $app = Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $rule -ErrorAction SilentlyContinue
    $prog = [string]$app.Program
    $isOllamaName = [string]$rule.DisplayName -match '(?i)ollama'
    $isOllamaProg = $prog -match '(?i)ollama\.exe$'
    if (-not $isOllamaName -and -not $isOllamaProg) { continue }
    if ($isOllamaProg -and $prog -and -not ($programs -contains $prog)) {
        $programs.Add($prog) | Out-Null
    }
    Remove-NetFirewallRule -Name $rule.Name -ErrorAction SilentlyContinue
    $removed++
    Write-Host "Removed '$($rule.DisplayName)' $($rule.Profile) $prog"
}

Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object {
    $_.DisplayName -like "$RulePrefix*" -or
    $_.DisplayName -like "$BlockPrefix*" -or
    $_.Name -like 'ChironAI-Ollama-*'
} | Remove-NetFirewallRule -ErrorAction SilentlyContinue

foreach ($candidate in $ExeCandidates) {
    if ((Test-Path -LiteralPath $candidate) -and -not ($programs -contains $candidate)) {
        $programs.Add($candidate) | Out-Null
    }
}

New-NetFirewallRule -Name 'ChironAI-Ollama-LAN-TCP' `
    -DisplayName "$RulePrefix TCP $ListenPort" `
    -Direction Inbound -Action Allow -Enabled True `
    -Profile Any `
    -Protocol TCP `
    -LocalPort $ListenPort `
    -RemoteAddress $RemoteCidrs | Out-Null

New-NetFirewallRule -Name 'ChironAI-Ollama-Block-Public-TCP' `
    -DisplayName "$BlockPrefix TCP $ListenPort" `
    -Direction Inbound -Action Block -Enabled True `
    -Profile Public `
    -Protocol TCP `
    -LocalPort $ListenPort | Out-Null

$index = 0
foreach ($prog in $programs) {
    $index++
    $suffix = if ($prog -match '(?i)\\Programs\\Ollama\\') { 'app' } else { "exe$index" }
    New-NetFirewallRule -Name "ChironAI-Ollama-LAN-TCP-$suffix" `
        -DisplayName "$RulePrefix TCP ($suffix)" `
        -Direction Inbound -Action Allow -Enabled True `
        -Profile Any `
        -Protocol TCP `
        -RemoteAddress $RemoteCidrs `
        -Program $prog | Out-Null
    Write-Host "Allow program $suffix from $($RemoteCidrs -join ', ')"
}

[Environment]::SetEnvironmentVariable('OLLAMA_HOST', $HostBind, 'Machine')
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', $HostBind, 'User')
Write-Host "OLLAMA_HOST=$HostBind (Machine + User). Restart Ollama / the ChironAI container to apply."

$ollama = Get-Process -Name 'ollama' -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host "ollama.exe is running (PID $($ollama.Id -join ', ')). Restart it so the new bind is used."
}

Write-Host "Removed $removed old Ollama inbound allows. TCP $ListenPort limited to $($RemoteCidrs -join ', '). Public $ListenPort blocked."
exit 0
