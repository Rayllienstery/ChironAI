"""Stop processes listening on known WebUI / rag_proxy ports (Windows)."""

from __future__ import annotations

import subprocess
import sys

from config import get_server_port_candidate_ports


def _kill_port(port: int) -> None:
    ps = (
        f"$p = {int(port)}; "
        "Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue "
        "| Select-Object -ExpandProperty OwningProcess -Unique "
        "| ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        check=False,
    )


def main() -> None:
    if sys.platform != "win32":
        return
    for port in get_server_port_candidate_ports():
        _kill_port(port)


if __name__ == "__main__":
    main()
