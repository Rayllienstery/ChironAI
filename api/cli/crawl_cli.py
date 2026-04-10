"""
CLI entrypoint for crawl: delegates to crawler_service (same as WebUI/app.py crawl).

Usage from project root:
  python -m api.cli.crawl_cli crawl [--dry-run] [--source ID]
  chironai-crawl   (after pip install -e modules/crawler_service)
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = os.environ.copy()
    env["CHIRONAI_PROJECT_ROOT"] = root
    env["CHIRONAI_WEBUI_DIR"] = os.path.join(root, "WebUI")
    _p = os.pathsep.join(
        [
            root,
            os.path.join(root, "modules", "crawler_service"),
            os.path.join(root, "modules", "html_md"),
        ]
    )
    env["PYTHONPATH"] = _p + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    argv = [sys.executable, "-m", "crawler_service.api.cli"] + (sys.argv[1:] or ["crawl"])
    sys.exit(subprocess.run(argv, cwd=root, env=env).returncode)


if __name__ == "__main__":
    main()
