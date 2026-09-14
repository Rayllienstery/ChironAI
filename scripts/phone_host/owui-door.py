#!/usr/bin/env python3
"""Always-on Open WebUI door. Run on the router (or any host that stays on).

iPhone opens http://<this-host>:9377/ → this process sends Wake-on-LAN,
waits until Open WebUI on the PC answers, then redirects the browser there.

Do not run this on the sleeping PC. Bind it on the Keenetic/Entware LAN
(or WireGuard gateway) only — never on the public WAN.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_OWUI = "http://192.168.50.115:3000"
DEFAULT_MAC = "74:56:3C:36:A3:76"
DEFAULT_IP = "192.168.50.115"
DEFAULT_BIND = "0.0.0.0"
DEFAULT_PORT = 9377
WOL_COOLDOWN_SEC = 15.0
OWUI_TIMEOUT_SEC = 2.0

_last_wol_mono = 0.0


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or not str(value).strip() else str(value).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed


OWUI_URL = _env("CHIRONAI_OWUI_URL", DEFAULT_OWUI).rstrip("/")
WOL_MAC = _env("CHIRONAI_WOL_MAC", DEFAULT_MAC)
WOL_IP = _env("CHIRONAI_WOL_IP", DEFAULT_IP)
WOL_UDP_PORT = _env_int("CHIRONAI_WOL_UDP_PORT", 9)
DOOR_BIND = _env("CHIRONAI_DOOR_BIND", DEFAULT_BIND)
DOOR_PORT = _env_int("CHIRONAI_DOOR_PORT", DEFAULT_PORT)
WOL_HOOK = _env("CHIRONAI_WOL_HOOK", "")


def _mac_bytes(mac: str) -> bytes:
    hex_part = "".join(ch for ch in mac if ch.isalnum())
    if len(hex_part) != 12:
        raise ValueError(f"MAC must be 6 bytes, got {mac!r}")
    return bytes.fromhex(hex_part)


def send_magic_packet() -> None:
    payload = b"\xff" * 6 + _mac_bytes(WOL_MAC) * 16
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(payload, (WOL_IP, WOL_UDP_PORT))
    finally:
        sock.close()
    if WOL_HOOK:
        subprocess.run(WOL_HOOK, shell=True, check=False, timeout=8)


def maybe_wake() -> None:
    global _last_wol_mono
    now = time.monotonic()
    if now - _last_wol_mono < WOL_COOLDOWN_SEC:
        return
    _last_wol_mono = now
    send_magic_packet()


def owui_is_up() -> bool:
    request = urllib.request.Request(OWUI_URL, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=OWUI_TIMEOUT_SEC) as response:
            return int(getattr(response, "status", 200) or 200) < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


WAKING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="3">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Waking PC</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.45; }
    p { max-width: 36rem; }
  </style>
</head>
<body>
  <h1>Waking the PC</h1>
  <p>Sent Wake-on-LAN. Open WebUI is not up yet. This page retries every 3 seconds, then opens the chat.</p>
  <p>Sleep takes about 15–40 seconds. A full shutdown takes longer (Windows + Docker + ChironAI).</p>
</body>
</html>
"""


class DoorHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _write(self, status: int, body: bytes, content_type: str, extra: list[tuple[str, str]] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in extra or []:
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _handle(self) -> None:
        if owui_is_up():
            dest = OWUI_URL + "/"
            body = f'<a href="{dest}">Open WebUI</a>\n'.encode("ascii")
            self._write(302, body, "text/html; charset=utf-8", [("Location", dest)])
            return
        maybe_wake()
        payload = WAKING_HTML.encode("utf-8")
        self._write(200, payload, "text/html; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle()


def main() -> None:
    server = ThreadingHTTPServer((DOOR_BIND, DOOR_PORT), DoorHandler)
    print(
        f"Open WebUI door on http://{DOOR_BIND}:{DOOR_PORT}/ -> {OWUI_URL}  MAC {WOL_MAC}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
