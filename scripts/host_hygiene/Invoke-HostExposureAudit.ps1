#Requires -Version 5.1
<#
.SYNOPSIS
  Audit this PC for network exposure and host security posture.

.DESCRIPTION
  Classifies TCP/UDP listeners (loopback vs LAN vs VPN vs wildcard), checks
  inbound firewall Allow-Any rules on sensitive apps, SMB shares on the VPN
  adapter, tunnel processes, Docker published ports, UPnP mappings, and diffs
  against a local baseline. Also runs Windows hardening checks (RDP, Defender,
  shares, remote-access apps, Secure Boot, etc.).

  -Deep additionally runs optional OSS tools if installed (HardeningKitty, Trivy).

  Does not scan other hosts. While PrivadoVPN is up, the public IPv4 is the VPN
  egress — that address is not this PC and is not probed.
#>
[CmdletBinding()]
param(
    [switch]$Notify,
    [switch]$NotifyAlways,
    [switch]$UpdateBaseline,
    [switch]$SkipUPnP,
    [switch]$Deep,
    [switch]$SkipHostSecurity,
    [string]$AllowlistPath,
    [string]$StateDir
)

$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir 'HostSecurityChecks.ps1')

if (-not $AllowlistPath) {
    $AllowlistPath = Join-Path $ScriptDir 'allowlist.json'
}
if (-not $StateDir) {
    $StateDir = Join-Path $env:LOCALAPPDATA 'ChironAI\host_hygiene'
}

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$HistoryDir = Join-Path $StateDir 'history'
New-Item -ItemType Directory -Force -Path $HistoryDir | Out-Null

function ConvertTo-UInt32Address([string]$Ip) {
    $bytes = [System.Net.IPAddress]::Parse($Ip).GetAddressBytes()
    if ($bytes.Length -ne 4) {
        throw "Not IPv4: $Ip"
    }
    if ([BitConverter]::IsLittleEndian) {
        [Array]::Reverse($bytes)
    }
    return [BitConverter]::ToUInt32($bytes, 0)
}

function Test-IPv4InCidr {
    param([string]$Ip, [string]$Cidr)
    if ($Ip -notmatch '^\d+\.\d+\.\d+\.\d+$') {
        return $false
    }
    $parts = $Cidr.Split('/')
    $prefix = [int]$parts[1]
    $network = ConvertTo-UInt32Address $parts[0]
    $addr = ConvertTo-UInt32Address $Ip
    if ($prefix -le 0) {
        return $true
    }
    if ($prefix -ge 32) {
        return ($addr -eq $network)
    }
    $mask = [uint32](([uint32]::MaxValue) -shl (32 - $prefix))
    return (($addr -band $mask) -eq ($network -band $mask))
}

function Test-IpInCidrs {
    param([string]$Ip, [object]$Cidrs)
    foreach ($cidr in @($Cidrs)) {
        if (Test-IPv4InCidr -Ip $Ip -Cidr ([string]$cidr)) {
            return $true
        }
    }
    return $false
}

function Get-BindScope {
    param([string]$Addr, $Cfg)
    if ([string]::IsNullOrWhiteSpace($Addr)) { return 'unknown' }
    if ($Addr -eq '127.0.0.1' -or $Addr -eq '::1') { return 'loopback' }
    if ($Addr -eq '0.0.0.0' -or $Addr -eq '::' -or $Addr -eq '[::]') { return 'wildcard' }
    if ($Addr -match '^fe80:') { return 'link-local' }
    if (Test-IPv4InCidr -Ip $Addr -Cidr $Cfg.lanCidr) { return 'lan' }
    if (Test-IpInCidrs -Ip $Addr -Cidrs $Cfg.wireguardLanCidrs) { return 'wg-lan' }
    if (Test-IpInCidrs -Ip $Addr -Cidrs $Cfg.otherTrustedCidrs) { return 'trusted' }
    if (Test-IpInCidrs -Ip $Addr -Cidrs $Cfg.vpnCidrs) { return 'vpn' }
    if ($Addr -match '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)') { return 'other-private' }
    if ($Addr -notmatch ':') { return 'public' }
    return 'ipv6-global'
}

function Get-ProcessInfo([int]$PidValue) {
    $p = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
    if (-not $p) {
        return [pscustomobject]@{ Name = '?'; Path = '' }
    }
    $path = ''
    try { $path = [string]$p.Path } catch { $path = '' }
    return [pscustomobject]@{ Name = $p.ProcessName; Path = $path }
}

function Test-IsSuppressed($Cfg, [string]$Key) {
    $prop = $Cfg.suppress.PSObject.Properties[$Key]
    if ($null -eq $prop) { return $false }
    return [bool]$prop.Value
}

function Test-ExpectedListener {
    param($Cfg, [string]$Protocol, [int]$Port, [string]$ProcessName, [string]$Scope)
    foreach ($row in @($Cfg.expectedListeners)) {
        if ([int]$row.port -ne $Port) { continue }
        if ([string]$row.protocol -and ([string]$row.protocol -ne $Protocol)) { continue }
        $wantProc = [string]$row.process
        if ($wantProc -and $wantProc -ne 'any' -and $ProcessName -notlike "$wantProc*") { continue }
        $wantScope = [string]$row.scope
        if ($wantScope -and $wantScope -ne 'any' -and $wantScope -ne $Scope) {
            if ($wantScope -eq 'wildcard' -and $Scope -in @('lan', 'wg-lan', 'trusted', 'vpn')) { continue }
            elseif ($wantScope -ne 'wildcard') { continue }
        }
        return $true
    }
    return $false
}

function Test-WindowsNoise {
    param([string]$Name, [int]$Port, [string]$Scope)
    if ($Name -in @('svchost', 'lsass', 'wininit', 'services', 'spoolsv', 'jhi_service') -and $Port -ge 49152) {
        return $true
    }
    if ($Scope -eq 'loopback') { return $true }
    if ($Scope -eq 'link-local') { return $true }
    return $false
}

function Add-Finding {
    param(
        [System.Collections.Generic.List[object]]$Bucket,
        [ValidateSet('critical', 'high', 'medium', 'low', 'info')][string]$Severity,
        [string]$Code,
        [string]$Title,
        [string]$Detail
    )
    foreach ($existing in $Bucket) {
        if ($existing.code -eq $Code -and $existing.title -eq $Title) {
            if ($Detail -and $existing.detail -notlike "*$Detail*") {
                $existing.detail = "$($existing.detail) | $Detail"
            }
            return
        }
    }
    $Bucket.Add([pscustomobject]@{
            severity = $Severity
            code     = $Code
            title    = $Title
            detail   = $Detail
        }) | Out-Null
}

function Show-Notification([string]$Title, [string]$Body) {
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $ni = New-Object System.Windows.Forms.NotifyIcon
        $ni.Icon = [System.Drawing.SystemIcons]::Warning
        $ni.Visible = $true
        $ni.BalloonTipTitle = $Title
        $ni.BalloonTipText = $Body
        $ni.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Warning
        $ni.ShowBalloonTip(12000)
        Start-Sleep -Seconds 2
        $ni.Dispose()
    } catch {
        Write-Warning "Toast failed: $($_.Exception.Message)"
    }
}

function Get-PublicIPv4 {
    $urls = @(
        'https://api.ipify.org?format=json',
        'https://ifconfig.me/ip'
    )
    foreach ($url in $urls) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8
            $text = $resp.Content.Trim()
            if ($text -match '"ip"\s*:\s*"([^"]+)"') {
                return $Matches[1]
            }
            if ($text -match '^\d+\.\d+\.\d+\.\d+$') {
                return $text
            }
        } catch {
            continue
        }
    }
    return $null
}

function Get-UPnPMappings {
    $result = [ordered]@{ igdFound = $false; location = $null; mappings = @(); error = $null }
    $udp = $null
    try {
        $udp = New-Object System.Net.Sockets.UdpClient
        $udp.Client.ReceiveTimeout = 1800
        $udp.Client.SendTimeout = 1800
        try { $udp.JoinMulticastGroup([System.Net.IPAddress]::Parse('239.255.255.250')) } catch { }
        $dest = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse('239.255.255.250'), 1900)
        $payload = "M-SEARCH * HTTP/1.1`r`nHOST: 239.255.255.250:1900`r`nMAN: `"ssdp:discover`"`r`nMX: 1`r`nST: urn:schemas-upnp-org:device:InternetGatewayDevice:1`r`n`r`n"
        $bytes = [Text.Encoding]::ASCII.GetBytes($payload)
        [void]$udp.Send($bytes, $bytes.Length, $dest)
        $remote = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Any, 0)
        $reply = $udp.Receive([ref]$remote)
        $text = [Text.Encoding]::ASCII.GetString($reply)
        if ($text -match '(?im)^LOCATION:\s*(\S+)') {
            $result.igdFound = $true
            $result.location = $Matches[1].Trim()
        }
    } catch {
        $result.error = $_.Exception.Message
        return [pscustomobject]$result
    } finally {
        if ($udp) { $udp.Close() }
    }

    if (-not $result.location) {
        return [pscustomobject]$result
    }

    try {
        $xml = Invoke-WebRequest -Uri $result.location -UseBasicParsing -TimeoutSec 5
        if ($xml.Content -notmatch 'WANIPConnection|WANPPPConnection') {
            return [pscustomobject]$result
        }
        $ctrl = $null
        if ($xml.Content -match '<controlURL>([^<]+)</controlURL>') {
            $ctrl = $Matches[1]
        }
        if (-not $ctrl) {
            return [pscustomobject]$result
        }
        $base = [Uri]$result.location
        if ($ctrl.StartsWith('http')) {
            $controlUri = $ctrl
        } else {
            $controlUri = '{0}://{1}:{2}{3}' -f $base.Scheme, $base.Host, $base.Port, $ctrl
        }
        $ns = 'urn:schemas-upnp-org:service:WANIPConnection:1'
        $mappings = New-Object System.Collections.Generic.List[object]
        for ($i = 0; $i -lt 24; $i++) {
            $soap = @"
<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:GetGenericPortMappingEntry xmlns:u="$ns">
      <NewPortMappingIndex>$i</NewPortMappingIndex>
    </u:GetGenericPortMappingEntry>
  </s:Body>
</s:Envelope>
"@
            try {
                $resp = Invoke-WebRequest -Uri $controlUri -Method Post -ContentType 'text/xml; charset="utf-8"' -Headers @{ SOAPACTION = "`"$ns#GetGenericPortMappingEntry`"" } -Body $soap -UseBasicParsing -TimeoutSec 4
                $body = $resp.Content
                $extPort = if ($body -match '<NewExternalPort>([^<]+)</NewExternalPort>') { $Matches[1] } else { '?' }
                $proto = if ($body -match '<NewProtocol>([^<]+)</NewProtocol>') { $Matches[1] } else { '?' }
                $intClient = if ($body -match '<NewInternalClient>([^<]+)</NewInternalClient>') { $Matches[1] } else { '?' }
                $intPort = if ($body -match '<NewInternalPort>([^<]+)</NewInternalPort>') { $Matches[1] } else { '?' }
                $desc = if ($body -match '<NewPortMappingDescription>([^<]*)</NewPortMappingDescription>') { $Matches[1] } else { '' }
                $enabled = if ($body -match '<NewEnabled>([^<]+)</NewEnabled>') { $Matches[1] } else { '' }
                $mappings.Add([ordered]@{
                        externalPort = $extPort
                        protocol     = $proto
                        internal     = "${intClient}:${intPort}"
                        description  = $desc
                        enabled      = $enabled
                    }) | Out-Null
            } catch {
                break
            }
        }
        $result.mappings = @($mappings)
    } catch {
        $result.error = $_.Exception.Message
    }
    return [pscustomobject]$result
}

if (-not (Test-Path -LiteralPath $AllowlistPath)) {
    throw "Allowlist not found: $AllowlistPath"
}

$Cfg = Get-Content -LiteralPath $AllowlistPath -Raw -Encoding UTF8 | ConvertFrom-Json
$findings = New-Object 'System.Collections.Generic.List[object]'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$utc = (Get-Date).ToUniversalTime().ToString('o')

$upAliases = @((Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' }).Name)
$nics = @(Get-NetIPAddress -AddressFamily IPv4, IPv6 -ErrorAction SilentlyContinue |
        Where-Object {
            $upAliases -contains $_.InterfaceAlias -and
            $_.IPAddress -notmatch '^fe80' -and
            $_.IPAddress -ne '::1' -and
            $_.IPAddress -notmatch '^127\.' -and
            $_.IPAddress -notmatch '^169\.254\.'
        } |
        Select-Object InterfaceAlias, AddressFamily, IPAddress, PrefixLength)

$vpnUp = $false
foreach ($nic in $nics) {
    foreach ($needle in @($Cfg.vpnAdapterNameContains)) {
        if ($nic.InterfaceAlias -like "*$needle*") {
            $vpnUp = $true
        }
    }
    if ((Get-BindScope -Addr $nic.IPAddress -Cfg $Cfg) -eq 'vpn') {
        $vpnUp = $true
    }
}

$publicIp = Get-PublicIPv4
$ethernetHasPublic = $false
foreach ($nic in $nics) {
    if ($nic.InterfaceAlias -eq 'Ethernet' -and (Get-BindScope -Addr $nic.IPAddress -Cfg $Cfg) -in @('public', 'ipv6-global')) {
        $ethernetHasPublic = $true
        Add-Finding $findings 'critical' 'public-nic' 'Ethernet has a public address' "$($nic.IPAddress) is on Ethernet. This PC is not behind NAT on that family."
    }
}

$listeners = New-Object 'System.Collections.Generic.List[object]'

Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = Get-ProcessInfo ([int]$_.OwningProcess)
    $scope = Get-BindScope -Addr $_.LocalAddress -Cfg $Cfg
    $listeners.Add([pscustomobject]@{
            protocol = 'TCP'
            address  = $_.LocalAddress
            port     = [int]$_.LocalPort
            pid      = [int]$_.OwningProcess
            process  = $proc.Name
            path     = $proc.Path
            scope    = $scope
        }) | Out-Null
}

Get-NetUDPEndpoint -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = Get-ProcessInfo ([int]$_.OwningProcess)
    $scope = Get-BindScope -Addr $_.LocalAddress -Cfg $Cfg
    $listeners.Add([pscustomobject]@{
            protocol = 'UDP'
            address  = $_.LocalAddress
            port     = [int]$_.LocalPort
            pid      = [int]$_.OwningProcess
            process  = $proc.Name
            path     = $proc.Path
            scope    = $scope
        }) | Out-Null
}

$ignorePorts = @($Cfg.ignoreWildcardSystemPorts | ForEach-Object { [int]$_ })
$ignoreProcs = @($Cfg.ignoreProcessNames | ForEach-Object { [string]$_ })

foreach ($row in $listeners) {
    $scope = [string]$row.scope
    $name = [string]$row.process
    $port = [int]$row.port
    $proto = [string]$row.protocol

    if (Test-WindowsNoise -Name $name -Port $port -Scope $scope) { continue }
    if ($name -in $ignoreProcs -and $scope -in @('loopback', 'link-local', 'wildcard', 'lan', 'wg-lan', 'trusted')) { continue }

    $expected = Test-ExpectedListener -Cfg $Cfg -Protocol $proto -Port $port -ProcessName $name -Scope $scope

    if ($scope -eq 'public' -or $scope -eq 'ipv6-global') {
        Add-Finding $findings 'critical' 'listen-public' "Listener on a public address: ${name}:$port/$proto" "$($row.address) $($row.path)"
        continue
    }

    if ($scope -eq 'vpn') {
        if ($name -in @('System') -and $port -in 137, 138, 139, 445) {
            if (-not (Test-IsSuppressed $Cfg 'smbOnVpn')) {
                Add-Finding $findings 'high' 'smb-on-vpn' 'SMB/NetBIOS is bound to the VPN' "Address $($row.address) port $port/$proto. File shares can leak onto PrivadoVPN if the adapter is Public."
            }
            continue
        }
        if ($port -eq 1900 -and $name -in @('System', 'svchost')) {
            if (-not (Test-IsSuppressed $Cfg 'ssdpOnVpn')) {
                Add-Finding $findings 'low' 'ssdp-on-vpn' 'SSDP is advertising on the VPN' $row.address
            }
            continue
        }
        if ($name -eq 'steam' -and (Test-IsSuppressed $Cfg 'steamOnVpn')) { continue }
        if ($expected) { continue }
        Add-Finding $findings 'high' 'listen-vpn' "Unexpected VPN listener: ${name}:$port/$proto" "$($row.address) $($row.path)"
        continue
    }

    if ($scope -eq 'wildcard') {
        if ($port -in $ignorePorts -and $name -in @('System', 'svchost', 'brave', 'ChatGPT Classic')) { continue }
        if ($name -eq 'System' -and $port -eq 445) {
            if ($vpnUp -and -not (Test-IsSuppressed $Cfg 'smbOnVpn')) {
                Add-Finding $findings 'high' 'smb-wildcard-v6' 'SMB listens on IPv6 wildcard (::445)' 'That bind includes the VPN adapter, not only Ethernet.'
            }
            continue
        }
        if ($expected) { continue }
        if ($name -in $ignoreProcs -and $port -ge 49152) { continue }
        Add-Finding $findings 'medium' 'listen-wildcard' "New wildcard listener: ${name}:$port/$proto" "0.0.0.0/:: plus firewall = LAN and possibly VPN. $($row.path)"
        continue
    }

    if ($scope -in @('lan', 'wg-lan', 'trusted') -and -not $expected) {
        if ($name -in $ignoreProcs) { continue }
        if ($name -eq 'System' -and $port -in 137, 138, 139, 445) { continue }
        Add-Finding $findings 'medium' 'listen-lan' "New LAN listener: ${name}:$port/$proto" "$($row.address) $($row.path)"
    }
}

$shares = @()
try {
    $shares = @(Get-SmbShare -ErrorAction Stop | Select-Object Name, Path, Description)
} catch {
    $shares = @()
}
$sensitiveShares = @($shares | Where-Object { $_.Name -in @($Cfg.sensitiveShareNames) })
$smbOnVpn = @($listeners | Where-Object { $_.process -eq 'System' -and $_.scope -eq 'vpn' -and $_.port -in 137, 138, 139, 445 })
if ($sensitiveShares.Count -gt 0 -and $smbOnVpn.Count -gt 0 -and -not (Test-IsSuppressed $Cfg 'smbOnVpn')) {
    $names = ($sensitiveShares | ForEach-Object { $_.Name }) -join ', '
    Add-Finding $findings 'high' 'shares-on-vpn' 'Sensitive SMB shares exist while SMB listens on the VPN' "Shares: $names"
}

$tunnelHits = @()
foreach ($procName in @($Cfg.tunnelProcessNames)) {
    $hits = @(Get-Process -Name $procName -ErrorAction SilentlyContinue)
    foreach ($hit in $hits) {
        $tunnelHits += $hit
        Add-Finding $findings 'critical' 'tunnel-process' "Tunnel process running: $($hit.ProcessName)" "PID $($hit.Id) $($hit.Path)"
    }
}

$dockerPublished = @()
$dockerErr = $null
try {
    $dockerOut = & docker ps --format '{{.Names}}|{{.Ports}}|{{.Status}}' 2>&1
    if ($LASTEXITCODE -eq 0 -and $dockerOut) {
        foreach ($line in @($dockerOut)) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            $parts = $line.Split('|')
            $ports = if ($parts.Count -gt 1) { $parts[1] } else { '' }
            $dockerPublished += [pscustomobject]@{ name = $parts[0]; ports = $ports; status = $(if ($parts.Count -gt 2) { $parts[2] } else { '' }) }
            if ($ports -match '0\.0\.0\.0:|:::') {
                $expectedDockerPorts = @()
                if ($Cfg.PSObject.Properties['expectedDockerPublishPorts']) {
                    $expectedDockerPorts = @($Cfg.expectedDockerPublishPorts | ForEach-Object { [int]$_ })
                }
                $hostPorts = New-Object 'System.Collections.Generic.List[int]'
                foreach ($match in [regex]::Matches($ports, '(?:0\.0\.0\.0|::):(\d+)')) {
                    $hostPort = [int]$match.Groups[1].Value
                    if (-not ($hostPorts -contains $hostPort)) {
                        $hostPorts.Add($hostPort) | Out-Null
                    }
                }
                $unexpectedPorts = @($hostPorts | Where-Object { $expectedDockerPorts -notcontains $_ })
                if ($hostPorts.Count -eq 0 -or $unexpectedPorts.Count -gt 0) {
                    Add-Finding $findings 'high' 'docker-publish' "Docker publishes a container to all interfaces: $($parts[0])" $ports
                }
            }
        }
    } elseif ($LASTEXITCODE -ne 0) {
        $raw = ($dockerOut | Out-String).Trim()
        if ($raw -match 'dockerDesktopLinuxEngine|cannot find the file|The system cannot find') {
            $dockerErr = 'Docker Desktop is not running'
        } else {
            $dockerErr = $raw
        }
    }
} catch {
    $dockerErr = $_.Exception.Message
}

$portProxy = (netsh interface portproxy show all 2>$null | Out-String).Trim()
if ($portProxy -and $portProxy -notmatch '^\s*$' -and $portProxy -match '\d+\.\d+\.\d+\.\d+') {
    Add-Finding $findings 'high' 'portproxy' 'Windows portproxy forwards are configured' $portProxy
}

$firewallWatch = New-Object 'System.Collections.Generic.List[object]'
$pattern = (($Cfg.sensitiveFirewallNamePatterns | ForEach-Object { [regex]::Escape($_) }) -join '|')
$fwRules = @(Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -match $pattern })

foreach ($rule in $fwRules) {
    $addr = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule -ErrorAction SilentlyContinue
    $port = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule -ErrorAction SilentlyContinue
    $app = Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $rule -ErrorAction SilentlyContinue
    $remote = @($addr.RemoteAddress) -join ','
    $localPort = @($port.LocalPort) -join ','
    $item = [pscustomobject]@{
        name      = $rule.DisplayName
        profile   = [string]$rule.Profile
        remote    = $remote
        protocol  = [string]$port.Protocol
        localPort = $localPort
        program   = [string]$app.Program
    }
    $firewallWatch.Add($item) | Out-Null

    $isAnyRemote = ($remote -eq 'Any' -or [string]::IsNullOrWhiteSpace($remote))
    $name = [string]$rule.DisplayName
    if (-not $isAnyRemote) { continue }

    if ($name -match 'Sunshine' -and -not (Test-IsSuppressed $Cfg 'sunshineFirewallAny')) {
        Add-Finding $findings 'high' 'fw-sunshine-any' 'Sunshine inbound firewall allows Any' "$($item.protocol) / profile $($item.profile). Moonlight should be LAN-only, same as RustDesk."
    } elseif ($name -match 'File and Printer Sharing \(Restrictive\) \(SMB-In\)' -and $item.profile -match 'Public' -and -not (Test-IsSuppressed $Cfg 'restrictiveSmbPublicAny')) {
        Add-Finding $findings 'high' 'fw-smb-public-any' 'Public-profile SMB allows Any on 445' 'If PrivadoVPN is classified as Public, shares are allowed from the VPN tunnel.'
    } elseif ($name -match 'ComfyUI Output' -and -not (Test-IsSuppressed $Cfg 'comfyOutputWan')) {
        Add-Finding $findings 'high' 'fw-comfy-output-any' 'ComfyUI output FTP/HTTP firewall allows Any' "Rule $name ports $($item.localPort). Restrict to $($Cfg.lanCidr) like ComfyUI SMB LAN."
    } elseif ($name -match 'ollama' -and $item.profile -match 'Public' -and -not (Test-IsSuppressed $Cfg 'ollamaPublicAny')) {
        Add-Finding $findings 'high' 'fw-ollama-public' 'Ollama inbound allow on Public / Any' ([string]$app.Program)
    } elseif ($name -match 'python' -and $item.profile -match 'Public' -and -not (Test-IsSuppressed $Cfg 'pythonPublicAny')) {
        Add-Finding $findings 'high' 'fw-python-public' 'Python inbound allow on Public / Any' ([string]$app.Program)
    } elseif ($name -match 'OpenSSH|Remote Desktop') {
        Add-Finding $findings 'high' 'fw-admin-any' "Admin service firewall allows Any: $name" "$($item.protocol) $($item.localPort) profile $($item.profile)"
    } elseif ($name -match 'RustDesk' -and $remote -eq 'Any') {
        Add-Finding $findings 'critical' 'fw-rustdesk-any' 'RustDesk firewall drifted back to Any' 'Re-run scripts/rustdesk/setup-lan-host.ps1'
    }
}

$upnp = $null
if (-not $SkipUPnP) {
    $upnp = Get-UPnPMappings
    if ($upnp.igdFound -and @($upnp.mappings).Count -gt 0) {
        foreach ($map in @($upnp.mappings)) {
            Add-Finding $findings 'high' 'upnp-mapping' "UPnP maps $($map.protocol) $($map.externalPort) -> $($map.internal)" ([string]$map.description)
        }
    }
}

if (-not $SkipHostSecurity) {
    Add-HostSecurityFindings -Findings $findings -Cfg $Cfg -Deep:$Deep
}

$baselinePath = Join-Path $StateDir 'baseline.json'
$listenerKeys = @(
    $listeners |
        Where-Object {
            $_.scope -notin @('loopback', 'link-local') -and
            $_.process -notin $ignoreProcs -and
            -not (Test-WindowsNoise -Name $_.process -Port ([int]$_.port) -Scope $_.scope)
        } |
        ForEach-Object { '{0}/{1}/{2}/{3}' -f $_.protocol, $_.scope, $_.port, $_.process } |
        Sort-Object -Unique
)
$previousKeys = @()
if ((Test-Path -LiteralPath $baselinePath) -and -not $UpdateBaseline) {
    try {
        $baseline = Get-Content -LiteralPath $baselinePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $previousKeys = @($baseline.listenerKeys)
        if ($previousKeys.Count -gt 0 -and $listenerKeys.Count -gt 0) {
            $newKeys = Compare-Object -ReferenceObject $previousKeys -DifferenceObject $listenerKeys -PassThru | Where-Object { $_.SideIndicator -eq '=>' }
            foreach ($key in @($newKeys)) {
                if ([string]$key -match '/loopback/') { continue }
                Add-Finding $findings 'medium' 'baseline-new' "New listener since baseline: $key" 'Run with -UpdateBaseline after you accept it.'
            }
        }
    } catch {
        Write-Warning "Baseline unreadable: $($_.Exception.Message)"
    }
}

$severityRank = @{ critical = 4; high = 3; medium = 2; low = 1; info = 0 }
$worst = 0
foreach ($f in $findings) {
    $rank = $severityRank[[string]$f.severity]
    if ($rank -gt $worst) { $worst = $rank }
}

$publicIpNote = if ($vpnUp) {
    'Public IPv4 is the VPN egress, not this PC. It is not scanned.'
} else {
    'VPN is down; this is likely the home ISP address. Check router forwards.'
}

$jsonPath = Join-Path $StateDir 'last-report.json'
$mdPath = Join-Path $StateDir 'last-report.md'
$historyPath = Join-Path $HistoryDir ((Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
$utf8 = New-Object System.Text.UTF8Encoding $true
$upnpFound = $false
$upnpMaps = @()
if ($upnp) {
    $upnpFound = [bool]$upnp.igdFound
    $upnpMaps = @($upnp.mappings | ForEach-Object { '{0} {1} -> {2}' -f $_.protocol, $_.externalPort, $_.internal })
}
$jsonBody = @{
    generatedAt       = $utc
    generatedLocal    = $stamp
    vpnUp             = $vpnUp
    publicIPv4        = $publicIp
    publicIpNote      = $publicIpNote
    ethernetHasPublic = $ethernetHasPublic
    nics              = @($nics | ForEach-Object { "$($_.InterfaceAlias)=$($_.IPAddress)" })
    findings          = @($findings | ForEach-Object { @{ severity = $_.severity; code = $_.code; title = $_.title; detail = $_.detail } })
    listeners         = @($listeners | Where-Object { $_.scope -notin @('loopback', 'link-local') } | ForEach-Object { '{0} {1}:{2} {3} {4}' -f $_.protocol, $_.address, $_.port, $_.scope, $_.process })
    shares            = @($shares | ForEach-Object { '{0}={1}' -f $_.Name, $_.Path })
    dockerPublished   = @($dockerPublished | ForEach-Object { '{0} {1}' -f $_.name, $_.ports })
    dockerError       = [string]$dockerErr
    upnpIgd           = $upnpFound
    upnpMappings      = $upnpMaps
    listenerKeys      = @($listenerKeys)
    allowlist         = $AllowlistPath
} | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText($jsonPath, $jsonBody, $utf8)
[System.IO.File]::WriteAllText($historyPath, $jsonBody, $utf8)

if ($UpdateBaseline -or -not (Test-Path -LiteralPath $baselinePath)) {
    $baselineObj = [ordered]@{ savedAt = $utc; listenerKeys = $listenerKeys }
    [System.IO.File]::WriteAllText($baselinePath, ($baselineObj | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding $true))
}

$bySev = @{
    critical = @($findings | Where-Object { $_.severity -eq 'critical' }).Count
    high     = @($findings | Where-Object { $_.severity -eq 'high' }).Count
    medium   = @($findings | Where-Object { $_.severity -eq 'medium' }).Count
    low      = @($findings | Where-Object { $_.severity -eq 'low' }).Count
    info     = @($findings | Where-Object { $_.severity -eq 'info' }).Count
}

$md = New-Object System.Text.StringBuilder
[void]$md.AppendLine("# Host security audit")
[void]$md.AppendLine("")
[void]$md.AppendLine("- Local time: $stamp")
[void]$md.AppendLine("- Mode: $(if ($Deep) { 'deep (OSS tools)' } else { 'standard' })$(if ($SkipHostSecurity) { ' + exposure-only' })")
[void]$md.AppendLine("- VPN up: $vpnUp")
[void]$md.AppendLine("- Public IPv4: $publicIp")
[void]$md.AppendLine("- Note: $publicIpNote")
[void]$md.AppendLine("- Findings: $($findings.Count) (critical=$($bySev.critical) high=$($bySev.high) medium=$($bySev.medium) low=$($bySev.low) info=$($bySev.info))")
[void]$md.AppendLine("")
if ($findings.Count -eq 0) {
    [void]$md.AppendLine("No findings.")
} else {
    $ordered = @($findings | Sort-Object @{ Expression = { $severityRank[$_.severity] }; Descending = $true }, code)
    [void]$md.AppendLine("| Severity | Code | Title |")
    [void]$md.AppendLine("|---|---|---|")
    foreach ($f in $ordered) {
        $title = ([string]$f.title).Replace('|', '/')
        [void]$md.AppendLine("| $($f.severity) | $($f.code) | $title |")
    }
    [void]$md.AppendLine("")
    foreach ($f in $ordered) {
        [void]$md.AppendLine("## $($f.severity) / $($f.code)")
        [void]$md.AppendLine("")
        [void]$md.AppendLine([string]$f.title)
        [void]$md.AppendLine("")
        [void]$md.AppendLine([string]$f.detail)
        [void]$md.AppendLine("")
    }
}
[System.IO.File]::WriteAllText($mdPath, $md.ToString(), (New-Object System.Text.UTF8Encoding $true))

Write-Host "Host security audit  $stamp  $(if ($Deep) { '[Deep]' } else { '[Standard]' })"
Write-Host "VPN: $vpnUp   Public IPv4: $publicIp"
Write-Host $publicIpNote
Write-Host "Counts: critical=$($bySev.critical) high=$($bySev.high) medium=$($bySev.medium) low=$($bySev.low) info=$($bySev.info)"
Write-Host ""
if ($findings.Count -eq 0) {
    Write-Host 'No findings.'
} else {
    @($findings | Sort-Object @{ Expression = { $severityRank[$_.severity] }; Descending = $true }, code) | ForEach-Object {
        '{0,-8} {1,-22} {2}' -f $_.severity, $_.code, $_.title
    } | Write-Host
}
Write-Host ""
Write-Host "Report: $mdPath"

$shouldNotify = $false
if ($NotifyAlways) { $shouldNotify = $true }
elseif ($Notify -and $worst -ge 3) { $shouldNotify = $true }

if ($shouldNotify) {
    $highs = @($findings | Where-Object { $_.severity -in @('critical', 'high') })
    $summary = if ($highs.Count -gt 0) {
        (($highs | Select-Object -First 3 | ForEach-Object { $_.title }) -join '; ')
    } else {
        'Audit finished with no high findings.'
    }
    Show-Notification -Title "Host exposure: $($highs.Count) high/critical" -Body $summary
}

if ($worst -ge 4) { exit 2 }
if ($worst -ge 3) { exit 1 }
exit 0
