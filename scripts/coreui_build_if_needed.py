"""Build CoreUI only when dist is missing or source inputs changed."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = REPO_ROOT / "CoreModules" / "CoreUI"
DIST_INDEX = FRONTEND / "dist" / "index.html"

WATCH_FILES = (
    FRONTEND / "index.html",
    FRONTEND / "vite.config.js",
    FRONTEND / "package.json",
    FRONTEND / "package-lock.json",
)

WATCH_DIRS = (FRONTEND / "src", FRONTEND / "public")


def _newest_mtime(path: Path) -> float | None:
    if path.is_file():
        return path.stat().st_mtime
    if not path.is_dir():
        return None

    newest: float | None = None
    for child in path.rglob("*"):
        if child.is_file():
            mtime = child.stat().st_mtime
            if newest is None or mtime > newest:
                newest = mtime
    return newest


def _force_build() -> bool:
    return (os.getenv("CHIRONAI_FORCE_COREUI_BUILD") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def needs_build() -> bool:
    if _force_build():
        return True
    if not DIST_INDEX.is_file():
        return True

    dist_mtime = DIST_INDEX.stat().st_mtime
    for watch_file in WATCH_FILES:
        mtime = _newest_mtime(watch_file)
        if mtime is not None and mtime > dist_mtime:
            return True

    for watch_dir in WATCH_DIRS:
        mtime = _newest_mtime(watch_dir)
        if mtime is not None and mtime > dist_mtime:
            return True

    return False


def _ensure_dependencies() -> int:
    vite_cmd = FRONTEND / "node_modules" / ".bin" / "vite.cmd"
    if vite_cmd.is_file():
        return 0

    print("Front-end dependencies are not installed; installing from package-lock.json...")
    print()
    lock = FRONTEND / "package-lock.json"
    cmd = ["npm.cmd", "ci"] if lock.is_file() else ["npm.cmd", "install"]
    result = subprocess.run(cmd, cwd=FRONTEND, check=False)
    if result.returncode != 0:
        print()
        print("Dependency installation failed. Check npm output above.")
        return result.returncode
    print()
    return 0


def main() -> int:
    if not FRONTEND.is_dir():
        print(f"ERROR: Front-end directory not found: {FRONTEND}")
        return 1
    if not (FRONTEND / "package.json").is_file():
        print(f"ERROR: package.json missing in {FRONTEND}.")
        return 1

    dep_err = _ensure_dependencies()
    if dep_err != 0:
        return dep_err

    if not needs_build():
        print("CoreUI build is up to date; skipping npm run build.")
        print("  (set CHIRONAI_FORCE_COREUI_BUILD=1 to force a rebuild)")
        return 0

    print("CoreUI sources changed or dist is missing; running npm run build...")
    print()
    result = subprocess.run(["npm.cmd", "run", "build"], cwd=FRONTEND, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
