#Requires -Version 5.1
# Remove leftover ComfyUI FTP/HTTP firewall holes. Does not touch SMB shares or pictures.
[CmdletBinding()]
param([switch]$Elevated)

$ErrorActionPreference = 'Stop'

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not $Elevated -and -not (Test-IsAdministrator)) {
    Write-Host 'Requesting Administrator to delete ComfyUI FTP/HTTP firewall rules...'
    $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, '-Elevated'
    )
    if ($proc.ExitCode -ne 0) {
        throw "Elevated cleanup failed with exit code $($proc.ExitCode)"
    }
    exit 0
}

if (-not (Test-IsAdministrator)) {
    throw 'Administrator is required.'
}

foreach ($name in @('ComfyUI Output FTP', 'ComfyUI Output HTTP')) {
    $rules = @(Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)
    if ($rules.Count -eq 0) {
        Write-Host "No rule: $name"
        continue
    }
    $rules | Remove-NetFirewallRule
    Write-Host "Deleted firewall rule: $name"
}

exit 0
