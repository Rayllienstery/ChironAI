#!/usr/bin/env python3
"""Run import smoke checks after editable installs (Phase 4 / Track E)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    target = REPO_ROOT / "tests" / "scripts" / "test_import_smoke.py"
    return subprocess.call(
        [sys.executable, "-m", "pytest", "-q", str(target)],
        cwd=REPO_ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
