"""
CLI entrypoint for local markdown ingest.

Delegates to WebUI/ingest_markdown_local.py.
Usage from project root:
  python -m api.cli.local_ingest_cli <markdown_dir> [--collection NAME]
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(root, "WebUI", "ingest_markdown_local.py")
    if not os.path.isfile(script):
        print("WebUI/ingest_markdown_local.py not found.", file=sys.stderr)
        sys.exit(1)
    argv = [sys.executable, script] + sys.argv[1:]
    sys.exit(subprocess.run(argv, cwd=root).returncode)


if __name__ == "__main__":
    main()
