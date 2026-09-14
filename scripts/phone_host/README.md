# Phone-host scripts

iPhone Shortcuts helpers for wake (router), sleep, ChironAI generation status,
and opening Open WebUI after the PC is up.

Start with [`docs/PHONE_HOST.md`](../../docs/PHONE_HOST.md). Shortcut steps: [`IOS_SHORTCUT.md`](IOS_SHORTCUT.md).

| File | Role |
|------|------|
| `phone-host.cmd` / `phone-host.ps1` | SSH entry: `status`, `sleep`, `wake-help` |
| `setup-openssh.ps1` | OpenSSH Server + iPhone key |
| `setup-nic-wake.ps1` | Magic packet + pattern-match WoL on the Ethernet NIC |
| `setup-logon-autostart.ps1` | Optional ChironAI start at logon (Shutdown/S5 only) |
| `owui-door.py` | Always-on HTTP door: WoL, wait, redirect to `:3000` |
| `router/owui-door.cgi` | Same door for Keenetic/Entware busybox httpd |
| `router-wake.examples.txt` | Keenetic / OpenWrt / MikroTik wake commands |
