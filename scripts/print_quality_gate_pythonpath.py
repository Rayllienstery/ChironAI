"""Print PYTHONPATH entries used by quality_gate.py (for shell scripts)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from quality_gate import _quality_gate_pythonpath  # noqa: E402


def main() -> int:
    print(os.pathsep.join(_quality_gate_pythonpath()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
