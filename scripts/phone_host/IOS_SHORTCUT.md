# iPhone Shortcut recipe: Chiron PC

Rebuild this in the Shortcuts app (iOS 18). One shortcut named **Chiron PC** with a menu, plus a second shortcut **Chiron Chat** for Open WebUI.

Pin **Chiron Chat** to the Home Screen (that is the daily path). Pin **Status** to the Action Button; add Wake/Sleep to Control Center.

Host values for this PC:

- SSH host: `192.168.50.115`
- User: Windows account that owns `C:\Users\Raylee\AI`
- Authentication: key `%USERPROFILE%\.ssh\chiron-iphone_ed25519` copied to the iPhone
- Script: `C:\Users\Raylee\AI\scripts\phone_host\phone-host.cmd`
- Open WebUI: `http://192.168.50.115:3000`
- Router door (if installed): `http://192.168.50.1:9377/`

Router SSH/HTTP is a second host (the WireGuard gateway). Fill that from `scripts/phone_host/router-wake.examples.txt`. Do not put the router admin password in git.

## Chiron Chat (Open WebUI when the PC may be asleep)

If the router door is running, this shortcut is one action: **Open URLs** `http://192.168.50.1:9377/`. The door sends WoL, waits, and redirects.

Without the door, build **Chiron Chat** as:

1. **Get Contents of URL** `http://192.168.50.115:3000`  
   - Method: GET  
   - Timeout: 3 seconds  
   - If this succeeds → **Open URLs** `http://192.168.50.115:3000` and stop
2. **Otherwise** wake via the router (pick one):
   - **Get Contents of URL** Keenetic RCI (see `router-wake.examples.txt`), or
   - **Run Script Over SSH** on the router (`etherwake` / `ndmc`)
3. **Repeat** 12 times:
   1. **Wait** 5 seconds
   2. **Get Contents of URL** `http://192.168.50.115:3000` (timeout 3 seconds)
   3. If it succeeds → **Open URLs** `http://192.168.50.115:3000` and stop
4. **Show Notification** `ПК не проснулся` if every attempt failed

Do not open Safari first and hope. The first request to `:3000` while the NIC is asleep will fail even if pattern-match wake is on. The shortcut (or the door) waits on purpose.

After Open WebUI is on screen, send the chat message as usual. If a cached PWA still has an old tab open, close it and use this shortcut so the session is live.

## Actions (Chiron PC menu)

1. **List** (menu): `Status`, `Wake`, `Sleep`, `Chat`
2. **If** selected is `Status`
   1. **Run Script Over SSH**
      - Host: `192.168.50.115`
      - User: your Windows username
      - Script: `C:\Users\Raylee\AI\scripts\phone_host\phone-host.cmd status`
      - Timeout: 5 seconds
   2. **If** SSH fails → **Show Notification** `ПК спит или недоступен`
   3. **Otherwise** → **Show Notification** with SSH stdout (`message` line)
3. **If** selected is `Wake`
   1. **Run Script Over SSH** (or **Get Contents of URL**) against the **router** using the matching line in `router-wake.examples.txt`
   2. **Wait** 20 seconds
   3. Repeat the Status SSH action (timeout 8 seconds)
   4. Notify `ПК включён` / `Chiron ещё стартует` / `ПК спит` from stdout
4. **If** selected is `Sleep`
   1. Run Status SSH first
   2. **If** stdout contains `BLOCKED` or `Generating` → notify `Не усыпляю: идёт генерация` and stop
   3. **Otherwise** **Run Script Over SSH** script `C:\Users\Raylee\AI\scripts\phone_host\phone-host.cmd sleep`
   4. Notify `Усыпляю ПК`
5. **If** selected is `Chat` → run the **Chiron Chat** shortcut above

Shortcuts SSH timeout = asleep. Do not open Safari. Keep each action as **Show Notification**, not **Show Result**, except Chat which opens Open WebUI.

## Control Center / Action Button

- Home Screen: **Chiron Chat** (or the door URL).
- Settings → Control Center → add **Shortcut** tiles for Wake and Sleep, or the whole **Chiron PC** menu.
- Settings → Action Button → Shortcut → a second shortcut that only runs the Status SSH action (safe default).

## Optional LAN HTTP (not required)

Only if you later bind a reverse proxy and set `CHIRONAI_PHONE_STATUS_TOKEN`:

- **Get Contents of URL** `http://192.168.50.115:8080/api/webui/host/phone-status`
- Header `X-Chiron-Phone-Token: <token>`
- Prefer SSH curl to localhost so the WebUI can stay on `127.0.0.1`.
