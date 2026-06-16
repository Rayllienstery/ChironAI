"""
Configuration loader for ChironAI.

Reads YAML config files from the local `config/` directory and exposes
typed dictionaries with sensible defaults. Environment variables can
override YAML values where appropriate.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - runtime error if dependency missing
    yaml = None  # type: ignore


_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _BASE_DIR / "config"
_RAG_SERVICE_DIR = _BASE_DIR / "CoreModules" / "RagService"
if _RAG_SERVICE_DIR.is_dir():
    _rag_svc_path = str(_RAG_SERVICE_DIR)
    if _rag_svc_path not in sys.path:
        sys.path.insert(0, _rag_svc_path)

try:
    import rag_service.config as _rsc  # type: ignore
except Exception:  # safe: rag_service optional at import
    _rsc = None  # type: ignore


def _load_yaml(name: str) -> Dict[str, Any]:
    """
    Load a YAML config file from the config directory.

    If PyYAML is not installed or the file is missing/invalid, returns {}.
    """
    path = _CONFIG_DIR / name
    if yaml is None or not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:  # safe: missing/invalid yaml returns defaults
        return {}


_rag_cfg = _load_yaml("rag.yaml")
_server_cfg = _load_yaml("server.yaml")
_models_cfg = _load_yaml("models.yaml")
_retrieval_cfg = _load_yaml("retrieval.yaml")
_crawler_cfg = _load_yaml("crawler.yaml")
_indexing_cfg = _load_yaml("indexing.yaml")

RAG_CONFIG: Dict[str, Any] = _rag_cfg.get("rag", {})
SERVER_CONFIG: Dict[str, Any] = _server_cfg.get("server", {})
QDRANT_CONFIG: Dict[str, Any] = _server_cfg.get("qdrant", {})
OLLAMA_CONFIG: Dict[str, Any] = _models_cfg.get("ollama", {})
RETRIEVAL_CONFIG: Dict[str, Any] = _retrieval_cfg.get("retrieval", {})
CRAWLER_CONFIG: Dict[str, Any] = _crawler_cfg.get("crawler", {})
INDEXING_CONFIG: Dict[str, Any] = _indexing_cfg.get("indexing", {})
LLM_PROXY_SERVER_CONFIG: Dict[str, Any] = _server_cfg.get("llm_proxy", {})
EXTENSIONS_CONFIG: Dict[str, Any] = _server_cfg.get("extensions", {})
DEFAULT_EXTENSIONS_REGISTRY_URL = (
    "https://raw.githubusercontent.com/Rayllienstery/ChironAI-Extensions-Registry/main/extensions.json"
)
DEFAULT_EXTENSIONS_LOCAL_REGISTRY_FALLBACK = "extensions/registry/extensions.json"
DEFAULT_EXTENSIONS_BLOCKLIST_URL = "extensions/registry/blocklist.json"
DEFAULT_EXTENSIONS_REMOTE_BLOCKLIST_URL = (
    "https://raw.githubusercontent.com/Rayllienstery/ChironAI-Extensions-Registry/main/blocklist.json"
)
