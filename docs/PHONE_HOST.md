# Phone host: wake, sleep, and Open WebUI from iPhone

iPhone Shortcuts control a Windows PC over the existing WireGuard LAN. Wake uses
the always-on router (Wake-on-LAN). Sleep and status use Windows OpenSSH plus a
compact ChironAI endpoint. The management WebUI stays on `127.0.0.1`; the phone
never needs the full `/api/webui` surface.

Open WebUI (`http://192.168.50.115:3000`) runs **on the PC**. A powered-off PC
cannot receive a chat message. The iPhone talks to the router (or a tiny door
process on the router), the router wakes the PC, then the phone opens Open WebUI.

Checked on this PC (`RayleePC`, 2026-09-03):

| Item | Value |
|------|--------|
| Sleep | S3 available. Hibernate and Fast Startup are off. |
| NIC | Ethernet, Realtek 2.5GbE, `74-56-3C-36-A3-76` |
| LAN IP | `192.168.50.115` (reserve this in DHCP) |
| Wake on Magic Packet | Enabled |
| Shutdown Wake-On-Lan | Enabled |
| `DeviceWakeUpEnable` | True |
| OpenSSH Server | Not installed (`sshd.exe` missing). Client `ssh.exe` is present. |

BIOS Wake-on-LAN and the router static ARP still need a one-time human check.

## Prefer Sleep, not Shutdown

Use the iPhone **Sleep** action (S3). ChironAI, Docker, and Open WebUI stay in
RAM. After WoL they are ready in about 15–40 seconds.

A full **Shutdown** (S5) also wakes if BIOS + Shutdown Wake-On-Lan are on, but
Windows must boot, Docker Desktop must start, Open WebUI must come up
(`unless-stopped`), and ChironAI must start. That is minutes, not seconds, and
needs logon autostart:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\phone_host\setup-logon-autostart.ps1
```

Enable Docker Desktop → **Start Docker Desktop when you sign in**. Windows
auto-login is a separate OS choice if you do not want to type a password after
S5 wake.

## CoreUI tab

CoreUI → **iPhone PC** lists `phone-host.ps1` and `setup-openssh.ps1` with an enable switch.
Disabled scripts exit with `SCRIPT_DISABLED` and do not sleep or install OpenSSH. Flags are stored in
`scripts/phone_host/enabled.json` (gitignored) and in app settings.

The same tab shows the Open WebUI wake recipe (MAC, PC IP, chat URL, router door).

## Architecture

1. **Wake** — iPhone Shortcuts or the router door SSHs/HTTP to the always-on
   router and sends a directed magic packet to `192.168.50.115` /
   `74:56:3C:36:A3:76`. Broadcasts do not traverse WireGuard.
2. **Self-wake (optional)** — NIC **Wake on Pattern Match** plus a **static ARP**
   on the router. A TCP SYN to `:3000` from the iPhone can itself wake the NIC.
   The first HTTP request still times out; refresh after 20–40 s, or use the door
   so the phone waits with a page instead of an error.
3. **Status / sleep** — Shortcuts uses **Run Script Over SSH** against the PC.
   The script curls `http://127.0.0.1:<port>/api/webui/host/phone-status` and can sleep Windows.
4. **ChironAI** — already running after S3 wake. After S5, wait until `/live`
   answers (`chiron=starting` until then).

Do not bind the whole WebUI to `0.0.0.0` for this. Optional LAN HTTP for status only: set `CHIRONAI_PHONE_STATUS_TOKEN` and send `X-Chiron-Phone-Token`.

## PC checklist (once)

1. BIOS/UEFI: enable Wake-on-LAN / PME. Save and exit.
2. Elevated PowerShell from the repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\phone_host\setup-nic-wake.ps1
```

That turns on magic-packet + pattern-match wake and disables Realtek Energy-Efficient / Green Ethernet (those modes drop WoL). Confirm in the NIC advanced properties: **Wake on Magic Packet**, **Wake on Pattern Match**, **Shutdown Wake-On-Lan**.

3. Leave hibernation/Fast Startup off (already the case here).
4. Router: static DHCP for `74:56:3C:36:A3:76` → `192.168.50.115`, plus a **static ARP** binding so WoL and directed TCP still work after the NIC sleeps.
5. In an elevated PowerShell, from the repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\phone_host\setup-openssh.ps1
```

That installs OpenSSH Server, generates `%USERPROFILE%\.ssh\chiron-iphone_ed25519`, and appends the public key to `authorized_keys`.

6. Copy the **private** key onto the iPhone (Files app) and point the Shortcut SSH action at it. Do not reuse a password login.

## Open WebUI from iPhone (the actual chat path)

Do not bookmark only `http://192.168.50.115:3000` if the PC may be asleep. Safari
will fail before the PC is up.

**Best UX — router door (always-on):**

1. Copy `scripts/phone_host/router/owui-door.cgi` (or `scripts/phone_host/owui-door.py`) onto the Keenetic/Entware box.
2. Bind it on LAN/WireGuard only, port `9377`.
3. iPhone home-screen bookmark: `http://192.168.50.1:9377/`
4. Opening that URL sends WoL, shows “Waking the PC”, then redirects to Open WebUI.

Python door (any always-on Linux host on the LAN):

```sh
CHIRONAI_WOL_HOOK='ndmc -c "ip hotspot wake mac 74:56:3c:36:a3:76"' \
  python3 scripts/phone_host/owui-door.py
```

**Without Entware — iPhone Shortcut “Chiron Chat”:**

Follow [`scripts/phone_host/IOS_SHORTCUT.md`](../scripts/phone_host/IOS_SHORTCUT.md).
The shortcut tries Open WebUI, and if it is down it calls Keenetic RCI wake,
waits, then opens `:3000`.

Do not try to hold the chat POST on the router. Open WebUI streams are long SSE
sessions; the door only wakes and redirects. If a cached PWA sends a message
while the PC is still down, that one request fails — wait for the wake page,
then send again.

## Router wake (always-on sender)

iOS Shortcuts cannot send UDP. Put the magic-packet command on the router. Templates: [`scripts/phone_host/router-wake.examples.txt`](../scripts/phone_host/router-wake.examples.txt).

After WoL, wait 15–40 s, then run the PC `status` action until SSH answers (or
let the door poll Open WebUI).

## Status contract

`GET /api/webui/host/phone-status` (loopback, or token off-loopback):

```json
{
  "host": "awake",
  "chiron": "up",
  "generating": true,
  "kind": "llm",
  "detail": "qwen · 412 tok",
  "gpu_pct": 87,
  "active_traces": 1,
  "status": "Response",
  "message": "Generating: qwen · 412 tok"
}
```

`generating` is true when live LLM traces exist **or** GPU utilization is at least `CHIRONAI_PHONE_STATUS_GPU_BUSY_PCT` (default 15), so ComfyUI/Hermes still show up when they skip LlmProxy traces.

From SSH:

```bat
C:\Users\Raylee\AI\scripts\phone_host\phone-host.cmd status
C:\Users\Raylee\AI\scripts\phone_host\phone-host.cmd sleep
```

`sleep` refuses if `generating` is true.

## iPhone Shortcut

Follow [`scripts/phone_host/IOS_SHORTCUT.md`](../scripts/phone_host/IOS_SHORTCUT.md). Add **Chiron Chat** (or the door URL) to the Home Screen; put **Status** on the Action Button; put **Wake** / **Sleep** in Control Center.

## Recovery

| Symptom | Check |
|---------|--------|
| SSH timeout | PC is asleep or WireGuard is down. Run Wake or open the door URL, wait, retry Status. |
| `chiron starting` | Windows is up; wait for `Server ready` / autostart. |
| Open WebUI errors then works | First request raced the boot. Use the door or wait 20–40 s and retry. |
| WoL does nothing | BIOS WoL, static ARP, directed packet to `192.168.50.115`, not broadcast. Disable NIC EEE / Green Ethernet (`setup-nic-wake.ps1`). |
| Sleep does nothing | OpenSSH Server running; script path; S3 still available (`powercfg /a`). |
| Status 403 from LAN | Missing token, or curl localhost over SSH instead. |
| Chat after Shutdown stays down | Docker Desktop logon start + `setup-logon-autostart.ps1`. Prefer Sleep. |
