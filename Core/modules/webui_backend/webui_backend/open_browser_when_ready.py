"""Open the WebUI in the default browser once the backend responds."""

from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from config import get_server_port


def _open_browser_enabled() -> bool:
    return (os.getenv("CHIRONAI_OPEN_BROWSER") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def open_browser_when_ready(*, timeout_sec: float = 120.0) -> None:
    """Spawn a daemon thread that opens /webui after /api/webui/version returns 200."""
    if not _open_browser_enabled():
        return

    port = get_server_port()
    health_url = f"http://127.0.0.1:{port}/api/webui/version"
    webui_url = f"http://127.0.0.1:{port}/webui"

    def _worker() -> None:
        deadline = time.perf_counter() + timeout_sec
        while time.perf_counter() < deadline:
            try:
                with urllib.request.urlopen(health_url, timeout=1.5) as resp:
                    if resp.status == 200:
                        print(f"Server ready — opening browser at {webui_url}", flush=True)
                        webbrowser.open(webui_url)
                        return
            except (OSError, urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.5)
        print(
            f"Backend is ready at {webui_url} (automatic browser open timed out).",
            flush=True,
        )

    threading.Thread(
        target=_worker,
        name="open-browser-when-ready",
        daemon=True,
    ).start()


__all__ = ["open_browser_when_ready"]
