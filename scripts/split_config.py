"""Split config/__init__.py into loader.py, env.py, and thin __init__.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "config" / "__init__.py"
lines = INIT.read_text(encoding="utf-8").splitlines(keepends=True)

loader_header = "".join(lines[:79])
env_body = "".join(lines[80:])

env = '''"""Environment and runtime overrides for ChironAI configuration."""

from __future__ import annotations

import os
from typing import Any, Dict
from urllib.parse import urlparse

from config.loader import (
    CRAWLER_CONFIG,
    DEFAULT_EXTENSIONS_BLOCKLIST_URL,
    DEFAULT_EXTENSIONS_LOCAL_REGISTRY_FALLBACK,
    DEFAULT_EXTENSIONS_REGISTRY_URL,
    DEFAULT_EXTENSIONS_REMOTE_BLOCKLIST_URL,
    EXTENSIONS_CONFIG,
    INDEXING_CONFIG,
    LLM_PROXY_SERVER_CONFIG,
    OLLAMA_CONFIG,
    QDRANT_CONFIG,
    RAG_CONFIG,
    RETRIEVAL_CONFIG,
    SERVER_CONFIG,
    _rsc,
    _server_cfg,
)

''' + env_body

init = '''"""
Configuration loader for ChironAI.

Reads YAML config files from the local `config/` directory and exposes
typed dictionaries with sensible defaults. Environment variables can
override YAML values where appropriate.
"""

from config.env import *  # noqa: F403
from config.loader import *  # noqa: F403
'''

(ROOT / "config" / "loader.py").write_text(loader_header, encoding="utf-8")
(ROOT / "config" / "env.py").write_text(env, encoding="utf-8")
INIT.write_text(init, encoding="utf-8")
print(
    f"loader: {len(loader_header.splitlines())} lines, "
    f"env: {len(env.splitlines())} lines, "
    f"init: {len(init.splitlines())} lines"
)
