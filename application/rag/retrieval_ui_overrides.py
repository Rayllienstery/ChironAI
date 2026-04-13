"""
Retrieval booleans overridable from WebUI (stored in ``proxy_settings`` JSON).

Same pattern as ``hybrid_sparse_enabled``: if the key is present in persisted
``proxy_settings``, it wins; otherwise ``retrieval.yaml`` / ``get_retrieval_bool``.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from config import get_retrieval_bool
except ImportError:
    get_retrieval_bool = lambda k, d=False: d  # type: ignore

# Keys mirrored in CoreUI RAG tab and POST /rag-model-settings.
RETRIEVAL_UI_BOOL_KEYS: frozenset[str] = frozenset(
    {
        "coverage_aware_selection",
        "concept_expansion_enabled",
        "coverage_gate_enabled",
        "coverage_retry_supplemental_search_enabled",
        "structured_rag_context_enabled",
    }
)


def retrieval_bool_with_ui_override(key: str, *, yaml_fallback: bool = False) -> bool:
    """
    Effective bool for retrieval behavior keys that the WebUI may persist.

    ``yaml_fallback`` is passed to ``get_retrieval_bool`` when the key is absent from YAML.
    """
    base = get_retrieval_bool(key, yaml_fallback)
    try:
        from infrastructure.database import get_settings_repository

        repo = get_settings_repository()
        raw = repo.get_app_setting("proxy_settings")
        if not raw or not str(raw).strip():
            return base
        ps: dict[str, Any] = json.loads(raw) if isinstance(raw, str) else {}
        if not isinstance(ps, dict) or key not in ps:
            return base
        return bool(ps[key])
    except Exception:
        return base


__all__ = ["RETRIEVAL_UI_BOOL_KEYS", "retrieval_bool_with_ui_override"]
