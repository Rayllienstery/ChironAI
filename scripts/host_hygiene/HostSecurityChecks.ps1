#Requires -Version 5.1
<#
.SYNOPSIS
  Extra host-security checks for Invoke-HostExposureAudit.ps1 (dot-sourced).
  Requires Add-Finding from the parent script scope.
#>

function Get-RegValue {
    param(
        [string]$Path,
        [string]$Name,
        $Default = $null
    )
    try {
        $item = Get-ItemProperty -LiteralPath $Path -ErrorAction Stop
        $prop = $item.PSObject.Properties[$Name]
        if ($null -eq $prop) { return $Default }
        return $prop.Value
    } catch {
        return $Default
    }
}

function Test-ServiceRunning([string]$Name) {
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) { return $false }
    return ($svc.Status -eq 'Running')
}

function Add-HostSecurityFindings {
    param(
        [Parameter(Mandatory)][System.Collections.Generic.List[object]]$Findings,
        [Parameter(Mandatory)]$Cfg,
        [switch]$Deep
    )

    # --- Network profiles on adapters ---
    try {
        $profiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue)
        foreach ($p in $profiles) {
            $alias = [string]$p.InterfaceAlias
            $netCat = [string]$p.NetworkCategory
            $isVpn = $false
            foreach ($needle in @($Cfg.vpnAdapterNameContains)) {
                if ($alias -like "*$needle*") { $isVpn = $true }
            }
            if ($isVpn -and $netCat -ne 'Public') {
                Add-Finding $Findings 'high' 'vpn-profile-not-public' "VPN adapter is not Public: $alias" "Category=$netCat. Privado should stay Public so LAN-only firewall rules do not apply to the tunnel."
            }
            if (-not $isVpn -and $alias -match 'Ethernet|Wi-Fi|WLAN' -and $netCat -eq 'Public') {
                Add-Finding $Findings 'medium' 'lan-profile-public' "Trusted NIC classified Public: $alias" 'Home LAN usually should be Private so file sharing / discovery work without Public Allow-Any rules.'
            }
        }
    } catch { }

    # --- Firewall enabled per profile ---
    try {
        foreach ($fp in @(Get-NetFirewallProfile -ErrorAction SilentlyContinue)) {
            if (-not [bool]$fp.Enabled) {
                Add-Finding $Findings 'critical' 'fw-disabled' "Windows Firewall disabled: $($fp.Name)" 'Inbound filtering is off for this profile.'
            }
        }
    } catch { }

    # --- Broad Public Allow-Any inbound (beyond name patterns) ---
    try {
        $pattern = (($Cfg.sensitiveFirewallNamePatterns | ForEach-Object { [regex]::Escape($_) }) -join '|')
        $noise = 'Core Networking|Delivery Optimization|Connected User Experiences|Microsoft Edge|Store|Your account|Cast to Device|mDNS|DIAL protocol|Wireless Display|Proximity|AllJoyn|Network Discovery|File and Printer Sharing \(LLMNR|File and Printer Sharing \(NB|File and Printer Sharing \(WSD|File and Printer Sharing \(SMB-In\) \(Restrictive\)|File and Printer Sharing \(Echo Request|Windows Media Player|Xbox|Bluetooth|Captive Portal|Connected Devices Platform|Work or school account|Wi-Fi Direct|WFD Driver|Steam|Steam Web Helper|Cortana|Desktop App Web Viewer|Win32WebViewHost|MicrosoftWindows\.Client\.CBS|ChatGPT'
        if ($Cfg.PSObject.Properties['firewallPublicAnyNoisePatterns']) {
            $noise = (@($Cfg.firewallPublicAnyNoisePatterns) -join '|')
        }
        $publicAnyCount = 0
        $publicAnyCap = 25
        if ($Deep.IsPresent) { $publicAnyCap = 80 }
        $publicAny = @(Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow -ErrorAction SilentlyContinue |
                Where-Object { $_.Profile -match 'Public|Any' })
        foreach ($rule in $publicAny) {
            $addr = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule -ErrorAction SilentlyContinue
            $remote = @($addr.RemoteAddress) -join ','
            if ($remote -ne 'Any' -and -not [string]::IsNullOrWhiteSpace($remote)) { continue }
            $name = [string]$rule.DisplayName
            if ($name -match $noise) { continue }
            if ($pattern -and $name -match $pattern) { continue }
            # Steam/game Allow-Any on Public is common installer noise — info unless Deep
            $looksLikeGame = ($name -match 'Classic|Gold|SIGNALIS|Divinity|Ghostrunner|Battle Brothers|Hollywood Animal|Gothic|Steam')
            $port = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule -ErrorAction SilentlyContinue
            $app = Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $rule -ErrorAction SilentlyContinue
            $localPort = @($port.LocalPort) -join ','
            $program = [string]$app.Program
            if ($looksLikeGame -and -not $Deep) {
                Add-Finding $Findings 'info' 'fw-public-any-game' "Public Allow-Any (game/app): $name" "Ports=$localPort Program=$program"
                continue
            }
            if ($publicAnyCount -ge $publicAnyCap) {
                Add-Finding $Findings 'medium' 'fw-public-any-more' "Additional Public Allow-Any rules omitted after $publicAnyCap" 'Re-run with -Deep for a longer list, or tighten Public profile.'
                break
            }
            Add-Finding $Findings 'medium' 'fw-public-any' "Public inbound Allow-Any: $name" "Ports=$localPort Program=$program Profile=$($rule.Profile)"
            $publicAnyCount++
        }
    } catch { }

    # --- RDP ---
    $fDenyTs = Get-RegValue 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' 'fDenyTSConnections' 1
    if ([int]$fDenyTs -eq 0) {
        $nla = Get-RegValue 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' 'UserAuthentication' 0
        $sev = if ([int]$nla -eq 1) { 'high' } else { 'critical' }
        $nlaText = if ([int]$nla -eq 1) { 'NLA on' } else { 'NLA OFF' }
        Add-Finding $Findings $sev 'rdp-enabled' "Remote Desktop is enabled ($nlaText)" 'Confirm firewall is LAN-only; disable RDP if unused.'
    }

    # --- WinRM ---
    if (Test-ServiceRunning 'WinRM') {
        try {
            $listeners = @(winrm enumerate winrm/config/listener 2>$null | Out-String)
            Add-Finding $Findings 'high' 'winrm-running' 'WinRM service is running' $(if ($listeners) { $listeners.Trim() } else { 'Could not enumerate listeners.' })
        } catch {
            Add-Finding $Findings 'high' 'winrm-running' 'WinRM service is running' $_.Exception.Message
        }
    }

    # --- Remote Registry ---
    if (Test-ServiceRunning 'RemoteRegistry') {
        Add-Finding $Findings 'high' 'remote-registry' 'Remote Registry service is running' 'Disable unless you need remote regedit.'
    }

    # --- SMBv1 ---
    try {
        $smb1 = Get-SmbServerConfiguration -ErrorAction SilentlyContinue
        if ($smb1 -and [bool]$smb1.EnableSMB1Protocol) {
            Add-Finding $Findings 'high' 'smb1-enabled' 'SMBv1 protocol is enabled' 'Legacy and worm-friendly. Disable with Set-SmbServerConfiguration -EnableSMB1Protocol $false.'
        }
    } catch { }

    # --- Guest account ---
    try {
        $guest = Get-LocalUser -Name 'Guest' -ErrorAction SilentlyContinue
        if ($guest -and $guest.Enabled) {
            Add-Finding $Findings 'high' 'guest-enabled' 'Local Guest account is enabled' 'Disable the Guest account.'
        }
    } catch { }

    # --- Auto logon ---
    $autoLogon = Get-RegValue 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' 'AutoAdminLogon' '0'
    if ([string]$autoLogon -eq '1') {
        $user = Get-RegValue 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' 'DefaultUserName' '?'
        Add-Finding $Findings 'high' 'auto-logon' "AutoAdminLogon is enabled for $user" 'Password may be stored in Winlogon; disable auto-logon on a multi-user / exposed host.'
    }

    # --- UAC ---
    $enableLua = Get-RegValue 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' 'EnableLUA' 1
    if ([int]$enableLua -eq 0) {
        Add-Finding $Findings 'critical' 'uac-disabled' 'UAC (EnableLUA) is disabled' 'Re-enable User Account Control.'
    }
    $consent = Get-RegValue 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' 'ConsentPromptBehaviorAdmin' 5
    if ([int]$consent -eq 0) {
        Add-Finding $Findings 'high' 'uac-prompt-never' 'UAC admin consent set to never prompt' 'ConsentPromptBehaviorAdmin=0.'
    }

    # --- Local administrators ---
    try {
        $admins = @(Get-LocalGroupMember -Group 'Administrators' -ErrorAction SilentlyContinue)
        $adminNames = @($admins | ForEach-Object { $_.Name })
        if ($adminNames.Count -gt 3) {
            Add-Finding $Findings 'medium' 'many-admins' "Administrators group has $($adminNames.Count) members" ($adminNames -join ', ')
        } else {
            Add-Finding $Findings 'info' 'admins' 'Local Administrators' ($adminNames -join ', ')
        }
    } catch { }

    # --- Defender ---
    try {
        $mp = Get-MpComputerStatus -ErrorAction Stop
        if (-not [bool]$mp.AntivirusEnabled) {
            Add-Finding $Findings 'critical' 'defender-off' 'Windows Defender antivirus is disabled' ''
        }
        if (-not [bool]$mp.RealTimeProtectionEnabled) {
            Add-Finding $Findings 'critical' 'defender-rtp-off' 'Defender real-time protection is off' ''
        }
        if ([bool]$mp.IsTamperProtected -eq $false) {
            Add-Finding $Findings 'medium' 'defender-tamper-off' 'Defender tamper protection is off' ''
        }
        $age = $null
        try { $age = [int]$mp.AntivirusSignatureAge } catch { }
        if ($null -ne $age -and $age -gt 7) {
            Add-Finding $Findings 'high' 'defender-sigs-stale' "Defender signatures are $age days old" 'Run Windows Update / MpCmdRun -SignatureUpdate.'
        }
        try {
            $prefs = Get-MpPreference -ErrorAction SilentlyContinue
            $exclusions = @($prefs.ExclusionPath) + @($prefs.ExclusionProcess) | Where-Object { $_ }
            foreach ($ex in $exclusions) {
                if ($ex -match '^[A-Za-z]:\\?$' -or $ex -eq 'C:\' -or $ex -eq 'C:' -or $ex -match '^[A-Za-z]:\\Users\\?$') {
                    Add-Finding $Findings 'critical' 'defender-exclusion-broad' "Broad Defender exclusion: $ex" 'Whole-volume or Users exclusions hide malware.'
                }
            }
        } catch { }
    } catch {
        Add-Finding $Findings 'medium' 'defender-unreadable' 'Could not read Defender status' $_.Exception.Message
    }

    # --- BitLocker ---
    try {
        $bl = @(Get-BitLockerVolume -ErrorAction SilentlyContinue | Where-Object { $_.VolumeType -eq 'OperatingSystem' })
        foreach ($vol in $bl) {
            if ($vol.ProtectionStatus -ne 'On') {
                Add-Finding $Findings 'medium' 'bitlocker-off' "OS volume $($vol.MountPoint) BitLocker is $($vol.ProtectionStatus)" 'Encrypt the system drive if the PC can leave home.'
            }
        }
    } catch {
        if ($Deep) {
            Add-Finding $Findings 'info' 'bitlocker-unreadable' 'BitLocker status unread (need admin?)' $_.Exception.Message
        }
    }

    # --- Secure Boot / TPM ---
    try {
        if ((Confirm-SecureBootUEFI -ErrorAction SilentlyContinue) -eq $false) {
            Add-Finding $Findings 'medium' 'secure-boot-off' 'Secure Boot is off' ''
        }
    } catch { }
    try {
        $tpm = Get-Tpm -ErrorAction SilentlyContinue
        if ($tpm -and -not [bool]$tpm.TpmReady) {
            Add-Finding $Findings 'low' 'tpm-not-ready' 'TPM is present but not ready' ("TpmPresent=$($tpm.TpmPresent) TpmReady=$($tpm.TpmReady)")
        }
    } catch { }

    # --- LLMNR ---
    $llmnr = Get-RegValue 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient' 'EnableMulticast'
    if ($null -eq $llmnr) {
        Add-Finding $Findings 'low' 'llmnr-default' 'LLMNR not disabled by policy' 'Name poisoning risk on untrusted LAN segments. Optional harden: EnableMulticast=0.'
    } elseif ([int]$llmnr -ne 0) {
        Add-Finding $Findings 'low' 'llmnr-on' 'LLMNR multicast is enabled' 'EnableMulticast!=0'
    }

    # --- Mobile Hotspot / ICS ---
    try {
        $ics = Get-Service SharedAccess -ErrorAction SilentlyContinue
        if ($ics -and $ics.Status -eq 'Running') {
            Add-Finding $Findings 'medium' 'ics-running' 'Internet Connection Sharing service is running' 'Can bridge LAN/VPN unexpectedly.'
        }
    } catch { }
    try {
        $tethering = Get-Service icssvc -ErrorAction SilentlyContinue
        if ($tethering -and $tethering.Status -eq 'Running') {
            Add-Finding $Findings 'medium' 'hotspot-svc' 'Mobile Hotspot service (icssvc) is running' 'Confirm you intend to share this PC connection.'
        }
    } catch { }

    # --- SMB share Everyone ACL ---
    try {
        foreach ($share in @(Get-SmbShare -ErrorAction SilentlyContinue)) {
            if ($share.Name -in @('IPC$')) { continue }
            foreach ($ace in @(Get-SmbShareAccess -Name $share.Name -ErrorAction SilentlyContinue)) {
                if ($ace.AccountName -match 'Everyone|Anonymous|Гость|Guest' -and $ace.AccessRight -match 'Full|Change') {
                    $sev = if ($share.Name -in @($Cfg.sensitiveShareNames)) { 'high' } else { 'medium' }
                    Add-Finding $Findings $sev 'share-everyone' "Share $($share.Name) grants $($ace.AccessRight) to $($ace.AccountName)" $share.Path
                }
            }
        }
    } catch { }

    # --- Remote access apps ---
    $remoteApps = @(
        'TeamViewer', 'TeamViewer_Service', 'AnyDesk', 'Splashtop', 'SRService',
        'remoting_host', 'Parsec', 'parsecd', 'vncserver', 'tvnserver', 'WinVNC',
        'UltraVNC', 'tightvnc', 'ammyy', 'RMS_Service', 'rutserv', 'AweSun', 'ToDesk', 'rustdesk'
    )
    if ($Cfg.PSObject.Properties['remoteAccessProcessNames']) {
        $remoteApps = @($Cfg.remoteAccessProcessNames)
    }
    foreach ($procName in $remoteApps) {
        foreach ($hit in @(Get-Process -Name $procName -ErrorAction SilentlyContinue)) {
            if ($hit.ProcessName -match '^(?i)rustdesk$') {
                Add-Finding $Findings 'info' 'remote-app' "Remote access app running: $($hit.ProcessName)" "PID $($hit.Id) $($hit.Path)"
                continue
            }
            Add-Finding $Findings 'high' 'remote-app' "Remote access app running: $($hit.ProcessName)" "PID $($hit.Id) $($hit.Path)"
        }
    }

    # --- RustDesk whitelist ---
    try {
        $rdToml = Join-Path $env:APPDATA 'RustDesk\config\RustDesk2.toml'
        if (Test-Path -LiteralPath $rdToml) {
            $text = Get-Content -LiteralPath $rdToml -Raw -ErrorAction SilentlyContinue
            $hasLan = $text -match '192\.168\.50\.'
            $hasWg = $text -match '10\.6\.'
            if ($text -notmatch 'whitelist\s*=') {
                Add-Finding $Findings 'critical' 'rustdesk-whitelist-empty' 'RustDesk whitelist key missing' $rdToml
            } elseif ($text -match "whitelist\s*=\s*''\s*$" -or $text -match 'whitelist\s*=\s*""\s*$') {
                Add-Finding $Findings 'critical' 'rustdesk-whitelist-empty' 'RustDesk whitelist is empty' $rdToml
            } elseif (-not $hasLan -or -not $hasWg) {
                $wl = if ($text -match "whitelist\s*=\s*'([^']*)'") { $Matches[1] }
                elseif ($text -match 'whitelist\s*=\s*"([^"]*)"') { $Matches[1] }
                else { '(unparsed)' }
                Add-Finding $Findings 'high' 'rustdesk-whitelist' 'RustDesk whitelist missing LAN or Keenetic WG' "whitelist='$wl' need 192.168.50.0/24 and 10.6.0.0/24"
            }
        }
    } catch { }

    # --- Unquoted service paths ---
    try {
        $limit = if ($Deep) { 40 } else { 15 }
        $services = Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
            Where-Object { $_.PathName -and $_.PathName -notlike '"*' -and $_.PathName -match ' ' -and $_.StartMode -ne 'Disabled' }
        $n = 0
        foreach ($svc in @($services)) {
            if ($n -ge $limit) { break }
            $exe = ($svc.PathName -split ' (?=[-/])')[0]
            if ($exe -match ' ' -and $exe -notmatch '^"') {
                Add-Finding $Findings 'medium' 'unquoted-service' "Unquoted service path: $($svc.Name)" $svc.PathName
                $n++
            }
        }
    } catch { }

    # --- Scheduled tasks from user-writable paths ---
    if ($Deep) {
        try {
            foreach ($task in @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.State -ne 'Disabled' })) {
                foreach ($action in @($task.Actions)) {
                    $exe = [string]$action.Execute
                    if ([string]::IsNullOrWhiteSpace($exe)) { continue }
                    if ($exe -match '\\Temp\\|\\Downloads\\|AppData\\Local\\Temp\\' -or $exe -match '^[A-Za-z]:\\Users\\[^\\]+\\Downloads\\') {
                        Add-Finding $Findings 'high' 'task-user-writable' "Scheduled task from user-writable path: $($task.TaskPath)$($task.TaskName)" $exe
                    }
                }
            }
        } catch { }
    }

    # --- Execution policy ---
    try {
        $ep = Get-ExecutionPolicy -List | Where-Object { $_.Scope -eq 'LocalMachine' }
        if ($ep -and [string]$ep.ExecutionPolicy -eq 'Unrestricted') {
            Add-Finding $Findings 'low' 'ps-unrestricted' 'LocalMachine ExecutionPolicy is Unrestricted' 'Prefer RemoteSigned.'
        }
    } catch { }

    # --- Windows Update age ---
    try {
        $lastSuccess = Get-RegValue 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\Results\Install' 'LastSuccessTime'
        if ($lastSuccess) {
            $parsed = [datetime]::MinValue
            if ([datetime]::TryParse([string]$lastSuccess, [ref]$parsed)) {
                $days = ((Get-Date) - $parsed).TotalDays
                if ($days -gt 45) {
                    Add-Finding $Findings 'medium' 'wu-stale' "Last successful Windows Update install ~$([int]$days) days ago" $lastSuccess
                }
            }
        }
    } catch { }

    # --- Teredo / 6to4 ---
    try {
        foreach ($t in @(Get-NetIPInterface -AddressFamily IPv6 -ErrorAction SilentlyContinue |
                Where-Object { $_.InterfaceAlias -match 'Teredo|6to4|ISATAP' -and $_.ConnectionState -eq 'Connected' })) {
            Add-Finding $Findings 'medium' 'ipv6-transition' "IPv6 transition interface up: $($t.InterfaceAlias)" 'Can bypass IPv4-only firewall mental models.'
        }
    } catch { }

    # --- Docker TCP expose ---
    try {
        foreach ($line in @(& docker context ls --format '{{.Name}} {{.DockerEndpoint}}' 2>$null)) {
            if ($line -match 'tcp://0\.0\.0\.0|tcp://\[::\]') {
                Add-Finding $Findings 'critical' 'docker-tcp-expose' 'Docker context listens on wildcard TCP' $line
            }
        }
    } catch { }

    # --- WSL ---
    try {
        $wslConfig = Join-Path $env:USERPROFILE '.wslconfig'
        if (Test-Path -LiteralPath $wslConfig) {
            $wslText = Get-Content -LiteralPath $wslConfig -Raw
            if ($wslText -match '(?im)^\s*networkingMode\s*=\s*mirrored') {
                Add-Finding $Findings 'medium' 'wsl-mirrored' 'WSL networkingMode=mirrored' 'WSL services may appear on Windows LAN interfaces.'
            }
            if ($wslText -match '(?im)^\s*localhostForwarding\s*=\s*true') {
                Add-Finding $Findings 'info' 'wsl-localhost-forward' 'WSL localhostForwarding=true' $wslConfig
            }
        }
    } catch { }

    # --- OpenSSH ---
    $sshdConfig = 'C:\ProgramData\ssh\sshd_config'
    if (Test-Path -LiteralPath $sshdConfig) {
        $sshd = Get-Content -LiteralPath $sshdConfig -ErrorAction SilentlyContinue
        $pwdAuth = ($sshd | Where-Object { $_ -match '^\s*PasswordAuthentication\s+' } | Select-Object -Last 1)
        if ($pwdAuth -match 'yes') {
            Add-Finding $Findings 'medium' 'ssh-password-auth' 'OpenSSH PasswordAuthentication yes' 'Prefer keys only if phone Shortcuts allow it.'
        }
        if (Test-ServiceRunning 'sshd') {
            $scopes = @(Get-NetTCPConnection -State Listen -LocalPort 22 -ErrorAction SilentlyContinue | ForEach-Object {
                    if ($_.LocalAddress -eq '0.0.0.0' -or $_.LocalAddress -eq '::') { 'wildcard' }
                    elseif ($_.LocalAddress -match '^127\.') { 'loopback' }
                    else { $_.LocalAddress }
                })
            if ($scopes -contains 'wildcard') {
                Add-Finding $Findings 'high' 'ssh-wildcard' 'sshd listening on 0.0.0.0/::' 'Firewall must stay LAN+WG; do not Allow-Any on Public.'
            }
        }
    }

    if ($Deep) {
        Invoke-OptionalAuditTools -Findings $Findings
    }
}

function Invoke-OptionalAuditTools {
    param(
        [Parameter(Mandatory)][System.Collections.Generic.List[object]]$Findings
    )

    $toolsRoot = Join-Path $env:LOCALAPPDATA 'ChironAI\host_hygiene\tools'

    # HardeningKitty (scipag module: HardeningKitty.psm1)
    $hkDir = Join-Path $toolsRoot 'HardeningKitty'
    $hkMod = Join-Path $hkDir 'HardeningKitty.psm1'
    if (Test-Path -LiteralPath $hkMod) {
        try {
            $hkOut = Join-Path $env:LOCALAPPDATA 'ChironAI\host_hygiene\hardeningkitty'
            New-Item -ItemType Directory -Force -Path $hkOut | Out-Null
            $listsDir = Join-Path $hkDir 'lists'
            # Prefer author's machine list (practical); fall back to any machine CSV
            $findingList = Join-Path $listsDir 'finding_list_0x6d69636b_machine.csv'
            if (-not (Test-Path -LiteralPath $findingList)) {
                $findingList = @(Get-ChildItem -Path $listsDir -Filter 'finding_list*machine*.csv' -ErrorAction SilentlyContinue |
                        Sort-Object Name -Descending |
                        Select-Object -First 1 -ExpandProperty FullName)
            }
            if ($findingList -and (Test-Path -LiteralPath $findingList)) {
                Unblock-File -Path (Join-Path $hkDir '*') -ErrorAction SilentlyContinue
                Unblock-File -Path (Join-Path $listsDir '*') -ErrorAction SilentlyContinue
                Import-Module -Name $hkMod -Force
                $reportFile = Join-Path $hkOut ('hk-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.csv')
                Invoke-HardeningKitty -Mode Audit -FileFindingList $findingList -Report -ReportFile $reportFile | Out-Null
                if (Test-Path -LiteralPath $reportFile) {
                    $rows = @(Import-Csv -LiteralPath $reportFile)
                    $failed = @($rows | Where-Object {
                            [string]$_.TestResult -eq 'Failed' -or
                            ([string]$_.Severity -notin @('Passed', '') -and [string]$_.TestResult -ne 'Passed')
                        } | Where-Object { [string]$_.Severity -ne 'Passed' })
                    $rank = @{ High = 3; Critical = 4; Medium = 2; Low = 1 }
                    $failed = @($failed | Sort-Object @{ Expression = {
                                $s = [string]$_.Severity
                                if ($rank.ContainsKey($s)) { $rank[$s] } else { 0 }
                            }; Descending = $true })
                    $caps = @{ high = 25; medium = 20; low = 8 }
                    $seen = @{ high = 0; medium = 0; low = 0 }
                    $omitted = 0
                    foreach ($row in $failed) {
                        $sevRaw = ([string]$row.Severity).ToLowerInvariant()
                        $sev = 'medium'
                        if ($sevRaw -match 'crit|high') { $sev = 'high' }
                        elseif ($sevRaw -match 'low') { $sev = 'low' }
                        if ($seen[$sev] -ge $caps[$sev]) {
                            $omitted++
                            continue
                        }
                        $title = [string]$row.Name
                        if (-not $title) { $title = [string]$row.ID }
                        Add-Finding $Findings $sev 'hardeningkitty' "HardeningKitty: $title" ("ID=$($row.ID) Result=$($row.Result) Recommended=$($row.Recommended) File=$(Split-Path $reportFile -Leaf)")
                        $seen[$sev]++
                    }
                    $reported = $seen.high + $seen.medium + $seen.low
                    if ($reported -eq 0) {
                        Add-Finding $Findings 'info' 'hardeningkitty-ok' 'HardeningKitty audit finished with no Failed rows' $reportFile
                    } elseif ($omitted -gt 0) {
                        Add-Finding $Findings 'medium' 'hardeningkitty-more' "HardeningKitty: $omitted more failed checks omitted (caps high=$($caps.high) med=$($caps.medium) low=$($caps.low))" "$($failed.Count) failed total; full CSV: $reportFile"
                    }
                } else {
                    Add-Finding $Findings 'info' 'hardeningkitty-no-report' 'HardeningKitty ran but report CSV missing' $hkOut
                }
            } else {
                Add-Finding $Findings 'info' 'hardeningkitty-no-list' 'HardeningKitty lists missing' $listsDir
            }
        } catch {
            Add-Finding $Findings 'low' 'hardeningkitty-error' 'HardeningKitty failed' $_.Exception.Message
        }
    } else {
        Add-Finding $Findings 'info' 'hardeningkitty-missing' 'HardeningKitty not installed' 'Run Install-HostAuditTools.ps1'
    }

    # Trivy on running container images
    $trivyExe = $null
    $cmd = Get-Command trivy -ErrorAction SilentlyContinue
    if ($cmd) {
        $trivyExe = $cmd.Source
    } else {
        $candidate = Join-Path $toolsRoot 'trivy\trivy.exe'
        if (Test-Path -LiteralPath $candidate) { $trivyExe = $candidate }
    }
    if ($trivyExe) {
        try {
            $uniq = @(& docker ps --format '{{.Image}}' 2>$null | Sort-Object -Unique)
            foreach ($img in $uniq) {
                if ([string]::IsNullOrWhiteSpace($img)) { continue }
                $outFile = Join-Path $env:TEMP ('trivy-' + ($img -replace '[^a-zA-Z0-9._-]', '_') + '.json')
                & $trivyExe image --quiet --severity CRITICAL,HIGH --format json -o $outFile $img 2>$null
                if (-not (Test-Path -LiteralPath $outFile)) { continue }
                $doc = Get-Content -LiteralPath $outFile -Raw | ConvertFrom-Json
                $vulns = New-Object System.Collections.Generic.List[object]
                foreach ($r in @($doc.Results)) {
                    foreach ($v in @($r.Vulnerabilities)) { $vulns.Add($v) | Out-Null }
                }
                $crit = @($vulns | Where-Object { $_.Severity -eq 'CRITICAL' })
                $high = @($vulns | Where-Object { $_.Severity -eq 'HIGH' })
                if ($crit.Count -gt 0 -or $high.Count -gt 0) {
                    $sample = @($crit + $high | Select-Object -First 5 | ForEach-Object { "$($_.VulnerabilityID) $($_.PkgName)" }) -join '; '
                    Add-Finding $Findings 'high' 'trivy-image' "Trivy: $img has $($crit.Count) CRITICAL / $($high.Count) HIGH" $sample
                }
            }
        } catch {
            Add-Finding $Findings 'low' 'trivy-error' 'Trivy scan failed' $_.Exception.Message
        }
    } else {
        Add-Finding $Findings 'info' 'trivy-missing' 'Trivy not installed' 'winget install AquaSecurity.Trivy  OR Install-HostAuditTools.ps1'
    }
}
