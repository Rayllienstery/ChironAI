#Requires -Version 5.1
<#
.SYNOPSIS
  Bind RustDesk to the Ethernet LAN with direct IP, IP whitelist, and low-latency quality.

.DESCRIPTION
  Stops public rendezvous/relay, enables direct IP on 21118, allows Ethernet
  192.168.50.0/24 and Keenetic WireGuard 10.6.0.0/24, turns on NVENC H.264 at
  60 fps, and replaces the Any/Public firewall holes with those LAN rules.

  Windows will prompt for Administrator for the service and firewall steps.
#>
[CmdletBinding()]
param(
    [string]$LanCidr = '192.168.50.0/24',
    [string]$WgCidr = '10.6.0.0/24',
    [string]$LanIp = '192.168.50.115',
    [int]$DirectPort = 21118,
    [switch]$SkipService,
    [switch]$SkipFirewall,
    [switch]$Elevated
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RulePrefix = 'ChironAI RustDesk LAN'

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-RustDeskExe {
    $candidates = @(
        (Join-Path ${env:ProgramFiles} 'RustDesk\rustdesk.exe'),
        (Join-Path ${env:ProgramFiles} 'RustDesk\RustDesk.exe'),
        (Join-Path $env:LOCALAPPDATA 'RustDesk\rustdesk.exe')
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    throw 'rustdesk.exe was not found. Install RustDesk first.'
}

function Get-OptionMap([string]$Text) {
    $map = [ordered]@{}
    $inOptions = $false
    foreach ($line in ($Text -split "`r?`n")) {
        if ($line -match '^\s*\[options\]\s*$') {
            $inOptions = $true
            continue
        }
        if ($inOptions -and $line -match '^\s*\[') {
            break
        }
        if ($inOptions -and $line -match "^\s*([A-Za-z0-9_-]+)\s*=\s*'(.*)'\s*$") {
            $map[$Matches[1]] = $Matches[2]
        }
    }
    return $map
}

function Get-TopValue([string]$Text, [string]$Key) {
    foreach ($line in ($Text -split "`r?`n")) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*'(.*)'\s*$") {
            return $Matches[1]
        }
        if ($line -match '^\s*\[') {
            break
        }
    }
    return $null
}

function Set-RustDeskHostConfig {
    param(
        [string]$ConfigPath,
        [string]$Cidr,
        [string]$WgCidr = '10.6.0.0/24',
        [string]$Ip,
        [int]$Port
    )
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw "RustDesk config not found: $ConfigPath"
    }
    $original = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8
    $options = Get-OptionMap $original
    $unlockPin = Get-TopValue $original 'unlock_pin'
    if ($null -eq $unlockPin) { $unlockPin = '' }
    $trusted = Get-TopValue $original 'trusted_devices'
    if ($null -eq $trusted) { $trusted = '' }

    $options['verification-method'] = $(if ($options['verification-method']) { $options['verification-method'] } else { 'use-permanent-password' })
    $options['stop-service'] = 'N'
    $options['local-ip-addr'] = $Ip
    $options['direct-server'] = 'Y'
    $options['direct-access-port'] = [string]$Port
    $options['enable-lan-discovery'] = 'Y'
    $options['whitelist'] = if ($WgCidr) { "$Cidr,$WgCidr" } else { $Cidr }
    $options['custom-rendezvous-server'] = '127.0.0.1'
    $options['relay-server'] = '127.0.0.1'
    $options['allow-websocket'] = 'N'
    $options['enable-udp-punch'] = 'N'
    $options['enable-ipv6-punch'] = 'N'
    $options['disable-udp'] = 'N'
    $options['enable-hwcodec'] = 'Y'
    $options['enable-abr'] = 'N'
    $options['enable-directx-capture'] = 'Y'
    $options['use-texture-render'] = 'Y'
    $options['allow-d3d-render'] = 'Y'
    $options['allow-always-software-render'] = 'N'
    $options['image-quality'] = 'custom'
    $options['custom-image-quality'] = '80'
    $options['custom-fps'] = '60'
    $options['codec-preference'] = 'h264'
    $options['i444'] = 'Y'
    $options['show-quality-monitor'] = 'Y'
    $options['view-style'] = 'original'
    $options['av1-test'] = 'N'

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("rendezvous_server = '127.0.0.1:21116'")
    [void]$sb.AppendLine('nat_type = 1')
    [void]$sb.AppendLine('serial = 0')
    [void]$sb.AppendLine("unlock_pin = '$unlockPin'")
    [void]$sb.AppendLine("trusted_devices = '$trusted'")
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('[options]')
    foreach ($key in $options.Keys) {
        $value = [string]$options[$key]
        $escaped = $value.Replace("'", "''")
        [void]$sb.AppendLine("$key = '$escaped'")
    }
    $newText = $sb.ToString()
    if ($newText -eq $original) {
        Write-Host "Host config already LAN-only: $ConfigPath"
        return $false
    }
    Copy-Item -LiteralPath $ConfigPath -Destination ($ConfigPath + '.bak') -Force
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($ConfigPath, ($newText.TrimEnd() + "`r`n"), $utf8)
    Write-Host "Updated host config: $ConfigPath"
    return $true
}

function Set-RustDeskPeerQuality([string]$PeerPath) {
    if (-not (Test-Path -LiteralPath $PeerPath)) {
        return
    }
    $raw = Get-Content -LiteralPath $PeerPath -Raw -Encoding UTF8
    $updated = $raw
    $updated = [regex]::Replace($updated, "(?m)^image_quality = '.*'$", "image_quality = 'custom'")
    $updated = [regex]::Replace($updated, '(?m)^custom_image_quality = \[.*\]$', 'custom_image_quality = [80]')
    $updated = [regex]::Replace($updated, '(?m)^show_quality_monitor = .+$', 'show_quality_monitor = true')
    $updated = [regex]::Replace($updated, "(?m)^custom-fps = '.*'$", "custom-fps = '60'")
    $updated = [regex]::Replace($updated, "(?m)^codec-preference = '.*'$", "codec-preference = 'h264'")
    $updated = [regex]::Replace($updated, "(?m)^i444 = '.*'$", "i444 = 'Y'")
    if ($updated -notmatch "(?m)^i444 = ") {
        $updated = $updated -replace "(?m)^(\[options\])$", "`$1`r`ni444 = 'Y'"
    }
    if ($updated -eq $raw) {
        Write-Host "Peer quality already set: $PeerPath"
        return
    }
    Copy-Item -LiteralPath $PeerPath -Destination ($PeerPath + '.bak') -Force
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($PeerPath, ($updated.TrimEnd() + "`r`n"), $utf8)
    Write-Host "Updated peer quality: $PeerPath"
}

function Stop-RustDeskProcesses {
    $servicePid = 0
    $svc = Get-CimInstance Win32_Service -Filter "Name='RustDesk'" -ErrorAction SilentlyContinue
    if ($svc -and $svc.ProcessId) { $servicePid = [int]$svc.ProcessId }
    Get-CimInstance Win32_Process -Filter "Name='rustdesk.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        if ([int]$_.ProcessId -eq $servicePid) { return }
        $cmd = [string]$_.CommandLine
        if ($cmd -match '--service') { return }
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 400
}

function Install-RustDeskService([string]$Exe) {
    $service = Get-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-Host 'Installing RustDesk Windows service...'
        $installer = Start-Process -FilePath $Exe -ArgumentList '--install-service' -PassThru -WindowStyle Hidden
        $deadline = (Get-Date).AddSeconds(20)
        while ((Get-Date) -lt $deadline) {
            $service = Get-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
            if ($service) { break }
            Start-Sleep -Milliseconds 500
        }
        if ($installer -and -not $installer.HasExited) {
            Stop-Process -Id $installer.Id -Force -ErrorAction SilentlyContinue
        }
        $service = Get-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
    }
    if (-not $service) {
        throw 'RustDesk service was not installed. Approve the UAC prompt and rerun.'
    }
    if ($service.StartType -ne 'Automatic') {
        Set-Service -Name 'RustDesk' -StartupType Automatic
    }
    if ($service.Status -ne 'Running') {
        Start-Service -Name 'RustDesk'
    }
    Write-Host 'RustDesk service is running.'
}

function Set-RustDeskLanFirewall {
    param(
        [string[]]$Cidrs,
        [int]$Port,
        [string]$Exe
    )
    Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object {
        $_.DisplayName -match 'rustdesk' -or $_.Name -like "$RulePrefix*"
    } | Remove-NetFirewallRule -ErrorAction SilentlyContinue

    $programs = @(
        $Exe,
        (Join-Path $env:LOCALAPPDATA 'RustDesk\rustdesk.exe')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | ForEach-Object {
        (Resolve-Path -LiteralPath $_).Path
    } | Select-Object -Unique

    foreach ($program in $programs) {
        $suffix = if ($program -like '*Program Files*') { 'PF' } else { 'User' }
        New-NetFirewallRule -Name "ChironAI-RustDesk-LAN-TCP-$suffix" `
            -DisplayName "$RulePrefix TCP ($suffix)" `
            -Direction Inbound -Action Allow -Enabled True `
            -Profile Any `
            -Protocol TCP -LocalPort 21116,21117,21118,21119 `
            -RemoteAddress $Cidrs `
            -Program $program | Out-Null
        New-NetFirewallRule -Name "ChironAI-RustDesk-LAN-UDP-$suffix" `
            -DisplayName "$RulePrefix UDP ($suffix)" `
            -Direction Inbound -Action Allow -Enabled True `
            -Profile Any `
            -Protocol UDP -LocalPort 21116,21118,21119 `
            -Program $program `
            -RemoteAddress $Cidrs | Out-Null
    }

    Write-Host "Firewall inbound limited to $($Cidrs -join ', ') (all profiles)."
}

function Start-RustDeskUi([string]$Exe) {
    $running = Get-CimInstance Win32_Process -Filter "Name='rustdesk.exe'" |
        Where-Object { $_.CommandLine -notmatch '--service' }
    if ($running) {
        Write-Host 'RustDesk UI already running.'
        return
    }
    Start-Process -FilePath $Exe
    Write-Host 'Started RustDesk UI.'
}

if (-not $Elevated -and -not $SkipService -and -not $SkipFirewall -and -not (Test-IsAdministrator)) {
    $argList = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $PSCommandPath,
        '-LanCidr', $LanCidr,
        '-WgCidr', $WgCidr,
        '-LanIp', $LanIp,
        '-DirectPort', $DirectPort,
        '-Elevated'
    )
    Write-Host 'Requesting Administrator for service + firewall...'
    $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $argList -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "Elevated setup failed with exit code $($proc.ExitCode)"
    }
    Start-RustDeskUi (Get-RustDeskExe)
    Write-Host ''
    Write-Host "Connect from the LAN or Keenetic WireGuard as ${LanIp}:${DirectPort} (not the public RustDesk ID)."
    exit 0
}

$exe = Get-RustDeskExe
$configDir = Join-Path $env:APPDATA 'RustDesk\config'
$hostConfig = Join-Path $configDir 'RustDesk2.toml'
$peerConfig = Join-Path $configDir "peers\$($LanCidr.Split('.')[0]).$($LanCidr.Split('.')[1]).$($LanCidr.Split('.')[2]).100.toml"
if ($LanIp -match '^(\d+\.\d+\.\d+)\.') {
    $peerConfig = Join-Path $configDir "peers\$($Matches[1]).100.toml"
}

Stop-RustDeskProcesses
Set-RustDeskHostConfig -ConfigPath $hostConfig -Cidr $LanCidr -WgCidr $WgCidr -Ip $LanIp -Port $DirectPort | Out-Null
Set-RustDeskPeerQuality -PeerPath $peerConfig

if (-not $SkipFirewall) {
    if (-not (Test-IsAdministrator)) {
        throw 'Administrator is required to replace RustDesk firewall rules.'
    }
    Set-RustDeskLanFirewall -Cidrs @($LanCidr, $WgCidr) -Port $DirectPort -Exe $exe
}

if (-not $SkipService) {
    if (-not (Test-IsAdministrator)) {
        throw 'Administrator is required to install the RustDesk service.'
    }
    Install-RustDeskService -Exe $exe
}

if ($Elevated) {
    Start-RustDeskUi $exe
}

Write-Host ''
Write-Host "RustDesk allows $($LanCidr) and $($WgCidr). Connect to ${LanIp}:${DirectPort} (not the public RustDesk ID)."
Write-Host 'Quality: NVENC H.264, 60 fps, custom 80, 4:4:4, adaptive bitrate off.'
exit 0
