"""Stop processes listening on the configured WebUI / rag_proxy port (Windows)."""

from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import get_pass_proxy_v2_port, get_server_port


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
    _kill_port(get_pass_proxy_v2_port())


if __name__ == "__main__":
    main()
