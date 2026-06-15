"""
Effective hybrid sparse (dense + keyword sparse) flag for RAG indexing and retrieval.

Order: WebUI `proxy_settings.hybrid_sparse_enabled` when explicitly set; else `retrieval.yaml` hybrid_sparse_enabled.
"""

from __future__ import annotations

try:
    from config import get_retrieval_bool
except ImportError:
    get_retrieval_bool = lambda k, d: d  # type: ignore

from application.rag.proxy_settings_contract import load_proxy_settings, resolve_hybrid_sparse_enabled


def is_hybrid_sparse_enabled() -> bool:
    """True when hybrid sparse should be used for new indexing and for search (if collection supports it)."""
    default = get_retrieval_bool("hybrid_sparse_enabled", True)
    try:
        from infrastructure.database import get_settings_repository

        repo = get_settings_repository()
        proxy_settings = load_proxy_settings(repo)
        value, _source = resolve_hybrid_sparse_enabled(
            proxy_settings=proxy_settings,
            yaml_default=default,
        )
        return value
    except Exception:
        return default


__all__ = ["is_hybrid_sparse_enabled"]
