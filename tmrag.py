#!/usr/bin/env python3
"""
ChironAI CLI entry point.

Usage:
  python tmrag.py start
  python tmrag.py crawl [--dry-run]
  python tmrag.py index [--dry-run]
  python tmrag.py rebuild [--dry-run]
  python tmrag.py update [--dry-run]
  python tmrag.py ingest <markdown_dir> [--collection NAME]
  python tmrag.py proxy
  python tmrag.py test
  python tmrag.py test-single [url]

Or: python -m api.cli <command> ...
"""

from __future__ import annotations

import sys
import os

# Run from project root so that api.cli can resolve paths
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from api.cli.__main__ import main

if __name__ == "__main__":
    main()
