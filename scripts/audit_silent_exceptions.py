"""Advisory audit for silent ``except Exception: pass`` without ``# safe:`` justification."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(
    r"except Exception:\s*\n\s*pass\b",
    re.MULTILINE,
)
SAFE_ON_EXCEPT = re.compile(r"except Exception:.*#\s*safe:", re.IGNORECASE)


def iter_python_files() -> list[Path]:
    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", "logs"}
    out: list[Path] = []
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in skip_dirs for part in path.parts):
            continue
        out.append(path)
    return out


def find_unjustified_silent_passes() -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    for path in iter_python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in PATTERN.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            line = text.splitlines()[line_no - 1]
            if SAFE_ON_EXCEPT.search(line):
                continue
            prev = text.splitlines()[line_no - 2] if line_no >= 2 else ""
            if SAFE_ON_EXCEPT.search(prev):
                continue
            hits.append((path.relative_to(REPO_ROOT), line_no, line.strip()))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("report", "check"), default="report")
    args = parser.parse_args()
    hits = find_unjustified_silent_passes()
    if not hits:
        print("No unjustified silent except Exception: pass blocks found.")
        return 0
    print(f"Found {len(hits)} unjustified silent except Exception: pass block(s):")
    for path, line_no, line in hits[:50]:
        print(f"  {path}:{line_no}: {line}")
    if len(hits) > 50:
        print(f"  ... and {len(hits) - 50} more")
    return 1 if args.mode == "check" else 0


if __name__ == "__main__":
    sys.exit(main())
