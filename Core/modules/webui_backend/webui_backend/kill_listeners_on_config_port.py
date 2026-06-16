"""Stop processes listening on known WebUI / rag_proxy ports (Windows)."""

from __future__ import annotations

import re
import subprocess
import sys

from config import get_server_port_candidate_ports


def _kill_port(port: int) -> None:
    # Use netstat (27ms) instead of PowerShell Get-NetTCPConnection (1200ms+).
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return

    pattern = re.compile(
        rf"^\s+TCP\s+\S+:{re.escape(str(port))}\s+\S+\s+LISTENING\s+(\d+)",
        re.IGNORECASE,
    )
    pids: set[str] = set()
    for line in result.stdout.splitlines():
        m = pattern.match(line)
        if m:
            pids.add(m.group(1))

    for pid in pids:
        subprocess.run(
            ["taskkill", "/F", "/PID", pid],
            check=False,
            capture_output=True,
        )


def main() -> None:
    if sys.platform != "win32":
        return
    for port in get_server_port_candidate_ports():
        _kill_port(port)


if __name__ == "__main__":
    main()
