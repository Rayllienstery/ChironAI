"""
CLI entrypoint for WebUI app.py commands.

Delegates to WebUI/app.py. Usage from project root:
  python -m api.cli.crawl_cli start
  python -m api.cli.crawl_cli crawl [--dry-run] [--source ID]
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    app_py = os.path.join(root, "WebUI", "app.py")
    if not os.path.isfile(app_py):
        print("WebUI/app.py not found.", file=sys.stderr)
        sys.exit(1)
    argv = [sys.executable, app_py] + (sys.argv[1:] or ["crawl"])
    sys.exit(subprocess.run(argv, cwd=root).returncode)


if __name__ == "__main__":
    main()
