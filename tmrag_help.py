#!/usr/bin/env python3
"""
Interactive ChironAI shell: show help, then accept commands (e.g. start, crawl).
Window stays open — you type a command and it runs tmrag.py.

Run as script: python tmrag_help.py
Build exe (from project root): pyinstaller --onefile --console --name tmrag tmrag_help.py
Place the exe in project root; then run tmrag.exe — type "start", "crawl", etc.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def _project_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _python_exe() -> str:
    if getattr(sys, "frozen", False):
        for name in ("python", "python3", "py"):
            exe = shutil.which(name)
            if exe:
                return exe
        return "python"
    return sys.executable


def _run_tmrag(args: list[str]) -> int:
    root = _project_root()
    tmrag_py = os.path.join(root, "tmrag.py")
    if not os.path.isfile(tmrag_py):
        print(f"tmrag.py not found in {root}", file=sys.stderr)
        return 1
    cmd = [_python_exe(), tmrag_py] + args
    return subprocess.run(cmd, cwd=root).returncode


def main() -> None:
    root = _project_root()
    print("ChironAI — interactive shell (project root:", root, ")", flush=True)
    _run_tmrag(["--help"])
    print()
    while True:
        try:
            line = input("python tmrag.py ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit", "q"):
            break
        args = line.split()
        _run_tmrag(args)
        print()


if __name__ == "__main__":
    main()
