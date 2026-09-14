#Requires -Version 5.1
<#
.SYNOPSIS
  Limit inbound Python firewall rules to Ethernet LAN and Keenetic WireGuard.

.DESCRIPTION
  Removes Windows auto-allow Public/Any python.exe rules and replaces them
  with RemoteAddress 192.168.50.0/24 + 10.6.0.0/24. Loopback is unchanged.
  Ollama is Repair-OllamaLanFirewall.ps1.
#>
[CmdletBinding()]
param(
    [switch]$Elevated,
    [string[]]$RemoteCidrs = @('192.168.50.0/24', '10.6.0.0/24')
)

$ErrorActionPreference = 'Stop'
$RulePrefix = 'ChironAI Python LAN'

if ($RemoteCidrs.Count -eq 1 -and $RemoteCidrs[0] -match ',') {
    $RemoteCidrs = @($RemoteCidrs[0].Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-PythonSuffix([string]$Program) {
    $norm = $Program.ToLowerInvariant().Replace('/', '\')
    if ($norm -match '\\python312\\python\.exe$') { return 'python312' }
    if ($norm -match '\\python314\\python\.exe$') { return 'python314' }
    if ($norm -match '\\uv\\python\\cpython-3\.11') { return 'uv311' }
    if ($norm -match '\\cloud\\mega\\comfyui\\') { return 'comfy-mega' }
    if ($norm -match '\\comfyui\\python_embeded\\') { return 'comfy-embed' }
    $leaf = Split-Path (Split-Path $Program -Parent) -Leaf
    $safe = ($leaf -replace '[^A-Za-z0-9]+', '-').Trim('-')
    if (-not $safe) { $safe = 'python' }
    return $safe.Substring(0, [Math]::Min(24, $safe.Length))
}

if (-not $Elevated -and -not (Test-IsAdministrator)) {
    Write-Host 'Requesting Administrator to restrict Python inbound firewall...'
    $cidrs = ($RemoteCidrs | ForEach-Object { $_.ToString() }) -join ','
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

$inbound = @(Get-NetFirewallRule -Direction Inbound -Action Allow -ErrorAction SilentlyContinue)
$programs = New-Object 'System.Collections.Generic.List[string]'
$removed = 0
foreach ($rule in $inbound) {
    $app = Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $rule -ErrorAction SilentlyContinue
    $prog = [string]$app.Program
    if ($prog -notmatch '(?i)python(w)?\.exe$') { continue }
    if ($prog -match '(?i)ollama') { continue }
    if ($prog -and -not ($programs -contains $prog)) {
        $programs.Add($prog) | Out-Null
    }
    Remove-NetFirewallRule -Name $rule.Name -ErrorAction SilentlyContinue
    $removed++
    Write-Host "Removed '$($rule.DisplayName)' $($rule.Profile) $prog"
}

Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object {
    $_.DisplayName -like "$RulePrefix*" -or $_.Name -like 'ChironAI-Python-LAN*'
} | Remove-NetFirewallRule -ErrorAction SilentlyContinue

foreach ($prog in $programs) {
    $suffix = Get-PythonSuffix $prog
    New-NetFirewallRule -Name "ChironAI-Python-LAN-TCP-$suffix" `
        -DisplayName "$RulePrefix TCP ($suffix)" `
        -Direction Inbound -Action Allow -Enabled True `
        -Profile Any `
        -Protocol TCP `
        -RemoteAddress $RemoteCidrs `
        -Program $prog | Out-Null
    New-NetFirewallRule -Name "ChironAI-Python-LAN-UDP-$suffix" `
        -DisplayName "$RulePrefix UDP ($suffix)" `
        -Direction Inbound -Action Allow -Enabled True `
        -Profile Any `
        -Protocol UDP `
        -RemoteAddress $RemoteCidrs `
        -Program $prog | Out-Null
    Write-Host "Allow $suffix from $($RemoteCidrs -join ', ')"
}

Write-Host "Removed $removed old Python inbound allows. LAN+WG rules: $($programs.Count) interpreters."
exit 0
