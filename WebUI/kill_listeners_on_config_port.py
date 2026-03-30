"""Stop processes listening on the configured WebUI / rag_proxy port (Windows)."""

from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import get_server_port


def main() -> None:
    if sys.platform != "win32":
        return
    port = get_server_port()
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


if __name__ == "__main__":
    main()
