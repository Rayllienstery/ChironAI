"""Stop processes listening on the configured WebUI / rag_proxy port (Windows)."""

from __future__ import annotations

import subprocess
import sys

from config import get_server_port


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
    _kill_port(get_server_port())


if __name__ == "__main__":
    main()
