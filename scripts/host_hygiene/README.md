# Host security / exposure audit

Periodic check that this PC did not accidentally publish AI services, SMB
shares, or game-streaming ports beyond the home LAN — plus Windows hardening
highlights (RDP, Defender, shares, remote-access apps, UAC, etc.).

It does **not** port-scan the internet, the VPN egress IP, or other machines.
While PrivadoVPN is up, `api.ipify.org` returns the VPN exit node — that is
not this host.

## Modes

| Mode | Command | What runs |
|---|---|---|
| Standard (default) | `Invoke-HostExposureAudit.ps1` | Network exposure + native host security checks |
| Deep | `Invoke-HostExposureAudit.ps1 -Deep` | Standard + HardeningKitty (CIS) + Trivy (Docker CVEs) if installed |
| Exposure only | `Invoke-HostExposureAudit.ps1 -SkipHostSecurity` | Original network/VPN leak checks only |

Scheduled task stays on **standard** (toast on high/critical). Use `-Deep` manually when you want the noisy CIS/CVE dump.

## What it flags (standard)

**Network exposure**

- Listeners on a public address, the VPN tunnel, or `0.0.0.0` / `::` that are
  not in `allowlist.json`
- SMB / NetBIOS bound to PrivadoVPN (file shares such as ComfyUI and Hermes)
- Inbound firewall Allow-Any on Sunshine, Python, Ollama, ComfyUI output HTTP/FTP,
  Public-profile SMB, OpenSSH, RDP
- Extra Public-profile Allow-Any rules (capped list)
- RustDesk firewall / whitelist drift
- Tunnel processes (`ngrok`, `cloudflared`, `playit`, …)
- Docker `-p 0.0.0.0:…` publishes and Docker TCP contexts
- Windows portproxy
- Router UPnP port mappings (best-effort SSDP)

**Host security**

- Firewall disabled; VPN NIC not Public; LAN NIC wrongly Public
- RDP / WinRM / Remote Registry / SMBv1 / Guest / AutoAdminLogon / weak UAC
- Defender off, stale signatures, broad exclusions, tamper protection
- BitLocker / Secure Boot / TPM (best-effort)
- LLMNR left at default; ICS / Mobile Hotspot running
- SMB shares granting Everyone Change/Full
- Remote-access apps (TeamViewer, AnyDesk, …); RustDesk expected as info
- Unquoted service paths; stale Windows Update; IPv6 Teredo/6to4
- WSL mirrored networking; OpenSSH password auth / wildcard bind
- Local Administrators membership (info / medium if crowded)

Loopback-only sockets (ChironAI `127.0.0.1:8080`, EA App, Cursor) are ignored.

## Optional OSS tools (Deep)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_hygiene\Install-HostAuditTools.ps1
```

Installs:

- [HardeningKitty](https://github.com/scipag/HardeningKitty) → `%LOCALAPPDATA%\ChironAI\host_hygiene\tools\HardeningKitty`
- [Trivy](https://github.com/aquasecurity/trivy) via `winget` (`AquaSecurity.Trivy`)

Then:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_hygiene\Invoke-HostExposureAudit.ps1 -Deep
```

## Run once

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_hygiene\Invoke-HostExposureAudit.ps1
```

Or double-click `Invoke-HostExposureAudit.cmd`.

After you accept the current listener set:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_hygiene\Invoke-HostExposureAudit.ps1 -UpdateBaseline
```

## Schedule

Every 6 hours and at logon. Balloon tip only when something is high/critical.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_hygiene\Install-HostExposureAuditTask.ps1
```

Remove:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_hygiene\Install-HostExposureAuditTask.ps1 -Disable
```

Reports land in `%LOCALAPPDATA%\ChironAI\host_hygiene\` (`last-report.md`,
`last-report.json`, `history\`). HardeningKitty CSVs under `hardeningkitty\`.

## Repair SMB on VPN

If the audit reports `smb-on-vpn` / `shares-on-vpn`, unbind File and Printer
Sharing from PrivadoVPN and block 137/138/139/445 on the Public profile.
Ethernet LAN shares stay up. Windows will ask for Administrator:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_hygiene\Repair-SmbOnVpn.ps1
```

## Repair Sunshine / Moonlight firewall

Keep Moonlight from Ethernet and Keenetic WireGuard (`10.6.0.0/24`). Drop
the installer Allow-Any rules so PrivadoVPN cannot reach the stream:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_hygiene\Repair-SunshineLanFirewall.ps1
```

## Repair Python inbound firewall

Windows pops Public Allow-Any for every `python.exe` that listens. Replace those
with LAN + Keenetic WireGuard (`192.168.50.0/24`, `10.6.0.0/24`). Loopback
(ChironAI, local ComfyUI) is unchanged. Does not touch Ollama:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_hygiene\Repair-PythonLanFirewall.ps1
```

## Repair Ollama inbound firewall

Same CIDRs as Sunshine/Python. TCP `11434` from Ethernet and Keenetic WireGuard.
Public `11434` is blocked so Docker Allow-Any cannot leak onto Privado.
ChironAI on `127.0.0.1:11434` is unchanged. Phone/LAN use `192.168.50.115:11434`.
Sets `OLLAMA_HOST=0.0.0.0:11434` (restart Ollama or the container after):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\host_hygiene\Repair-OllamaLanFirewall.ps1
```

## Tuning

Edit `allowlist.json`:

- Add an `expectedListeners` row for a service you really want on LAN/VPN
- Extend `remoteAccessProcessNames` / `tunnelProcessNames`
- Set a `suppress.*` flag to `true` only after you understand the risk

Expected LAN services when they are running: Open WebUI `:3000`, RustDesk
`:21118` (firewall already LAN-only), Sunshine/Moonlight, OpenSSH `:22`.
ChironAI WebUI should stay on `127.0.0.1`.
