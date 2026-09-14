#!/bin/sh
# Keenetic / OpenWrt / Entware CGI door for Open WebUI.
# Install as the index CGI of a LAN-only busybox httpd on port 9377.
# Do not expose this port on the WAN.
#
#   opkg install etherwake  # or use ndmc on Keenetic
#   httpd -p 9377 -h /opt/share/www/owui-door
#   cp owui-door.cgi /opt/share/www/owui-door/index.cgi
#   chmod +x /opt/share/www/owui-door/index.cgi
#
# Optional: CHIRONAI_WOL_HOOK='ndmc -c "ip hotspot wake mac 74:56:3c:36:a3:76"'

OWUI_URL="${CHIRONAI_OWUI_URL:-http://192.168.50.115:3000}"
WOL_MAC="${CHIRONAI_WOL_MAC:-74:56:3C:36:A3:76}"
WOL_IP="${CHIRONAI_WOL_IP:-192.168.50.115}"
STAMP="${CHIRONAI_WOL_STAMP:-/tmp/chiron-owui-wol.stamp}"

owui_up() {
  wget -q -T 2 -O /dev/null "$OWUI_URL" 2>/dev/null && return 0
  curl -fsS --max-time 2 -o /dev/null "$OWUI_URL" 2>/dev/null && return 0
  return 1
}

send_wol() {
  now=$(date +%s)
  last=0
  if [ -f "$STAMP" ]; then
    last=$(cat "$STAMP" 2>/dev/null || echo 0)
  fi
  delta=$((now - last))
  if [ "$delta" -lt 15 ]; then
    return 0
  fi
  echo "$now" > "$STAMP"

  if [ -n "$CHIRONAI_WOL_HOOK" ]; then
    eval "$CHIRONAI_WOL_HOOK" >/dev/null 2>&1 || true
  fi
  if command -v ndmc >/dev/null 2>&1; then
    ndmc -c "ip hotspot wake mac $(echo "$WOL_MAC" | tr 'A-F' 'a-f')" >/dev/null 2>&1 || true
  fi
  if command -v etherwake >/dev/null 2>&1; then
    etherwake "$WOL_MAC" >/dev/null 2>&1 || true
  elif command -v ether-wake >/dev/null 2>&1; then
    ether-wake "$WOL_MAC" >/dev/null 2>&1 || true
  elif command -v wol >/dev/null 2>&1; then
    wol "$WOL_MAC" >/dev/null 2>&1 || true
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import socket; m=bytes.fromhex('${WOL_MAC}'.replace(':','').replace('-','')); p=b'\\xff'*6+m*16; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(p,('${WOL_IP}',9))" >/dev/null 2>&1 || true
  fi
}

if owui_up; then
  printf 'Status: 302 Found\r\n'
  printf 'Location: %s/\r\n' "$OWUI_URL"
  printf 'Cache-Control: no-store\r\n'
  printf 'Content-Type: text/html; charset=utf-8\r\n'
  printf '\r\n'
  printf '<a href="%s/">Open WebUI</a>\n' "$OWUI_URL"
  exit 0
fi

send_wol

printf 'Status: 200 OK\r\n'
printf 'Cache-Control: no-store\r\n'
printf 'Content-Type: text/html; charset=utf-8\r\n'
printf '\r\n'
cat <<'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="3">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Waking PC</title>
</head>
<body>
  <h1>Waking the PC</h1>
  <p>Sent Wake-on-LAN. Open WebUI is not up yet. This page retries every 3 seconds, then opens the chat.</p>
</body>
</html>
HTML
