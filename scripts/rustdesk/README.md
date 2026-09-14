# RustDesk LAN host

Keeps RustDesk on this PC reachable from Ethernet `192.168.50.0/24` and
Keenetic WireGuard `10.6.0.0/24` (phone on 5G), with a direct IP path (no
public ID/relay) and NVENC H.264 at 60 fps.

Windows will ask for Administrator — click **Yes**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\rustdesk\setup-lan-host.ps1
```

Or double-click `scripts/rustdesk/setup-lan-host.cmd`.

From the Mac on Ethernet, or the phone on the router WireGuard, connect to
**`192.168.50.115:21118`**, not the public RustDesk ID. On that client set codec H.264, 60 fps, and quality
Custom ~80. Quality monitor should show a direct session, not relay.
