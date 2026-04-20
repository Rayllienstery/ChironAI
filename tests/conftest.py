"""
Pytest configuration. Ensures project root is on sys.path for domain/application imports.
"""

from __future__ import annotations

import os
import shutil
import sys
import uuid
from pathlib import Path

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture
def tmp_path() -> Path:
    """
    Workspace-local tmp path fixture that avoids pytest's Windows ACL edge case
    in this environment.
    """
    tmp_root = Path(_ROOT) / ".tmp_test_local"
    tmp_root.mkdir(parents=True, exist_ok=True)
    path = tmp_root / f"case-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
