"""
Effective hybrid sparse (dense + keyword sparse) flag for RAG indexing and retrieval.

Order: WebUI `proxy_settings.hybrid_sparse_enabled` when explicitly set; else `retrieval.yaml` hybrid_sparse_enabled.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from config import get_retrieval_bool
except ImportError:
    get_retrieval_bool = lambda k, d: d  # type: ignore


def is_hybrid_sparse_enabled() -> bool:
    """True when hybrid sparse should be used for new indexing and for search (if collection supports it)."""
    default = get_retrieval_bool("hybrid_sparse_enabled", True)
    try:
        from infrastructure.database import get_settings_repository

        repo = get_settings_repository()
        raw = repo.get_app_setting("proxy_settings")
        if not raw or not str(raw).strip():
            return default
        ps: dict[str, Any] = json.loads(raw) if isinstance(raw, str) else {}
        if not isinstance(ps, dict) or "hybrid_sparse_enabled" not in ps:
            return default
        return bool(ps["hybrid_sparse_enabled"])
    except Exception:
        return default


__all__ = ["is_hybrid_sparse_enabled"]
