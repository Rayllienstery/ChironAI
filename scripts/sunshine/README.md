# Moonlight quick menu (Sunshine)

Adds extra tiles next to **Steam Big Picture** in Moonlight:

| Tile | Action |
|------|--------|
| Cursor | Cursor IDE (`--classic`) |
| Cursor Agents | Cursor Agents Window (`--glass`) |
| Playnite | Playnite Fullscreen (`Playnite.FullscreenApp.exe`). Sunshine `undo` closes it when the Moonlight stream ends. |
| YouTube | Brave YouTube app (`--app-id`). Closes the YouTube window when the stream ends. |
| Brave | Brave Browser (`--new-window`). Closes Brave windows when the stream ends. |
| Sleep | Sleep the PC (S3). Refuses if ChironAI is generating. |
| Restart Docker | `docker desktop restart` |
| Restart ChironAI | Stop the WebUI listener and start `python -m webui_backend.rag_proxy` |
| Restart PC | Reboot Windows. Refuses if ChironAI is generating. |

## HD stream → dongle + Switch mode

`global_prep_cmd` runs `on-stream-display.ps1` on every stream (except Sleep/Restart*):

- Client ≤ 1920×1080 (Switch HD/720p) → video to HDMI dongle + **1920×1080@60** + UI scale 125%
- Stream end (if that fired) → LG **2560×1440@120** + scale 100%
- 2K clients leave the current monitor alone

**Requires** `C:\Users\Raylee\Documents\switch_display.ahk` running (Sunshine prep cannot change displays itself; it signals AHK). Log: `scripts/sunshine/state/on-stream-display.log`

Install into Sunshine (once). Windows will ask for Administrator permission — click **Yes**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sunshine\install-apps.ps1
```

Or double-click `scripts\sunshine\install-apps.cmd`. Then reopen Moonlight (or rescan the PC) so the new apps appear.

Sleep, reboot, and Restart ChironAI refuse if ChironAI is generating. Pass `-Force` on the host script to override.
