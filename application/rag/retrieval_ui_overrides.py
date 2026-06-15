"""
Retrieval booleans overridable from WebUI (stored in ``proxy_settings`` JSON).

Same pattern as ``hybrid_sparse_enabled``: if the key is present in persisted
``proxy_settings``, it wins; otherwise ``retrieval.yaml`` / ``get_retrieval_bool``.
"""

from __future__ import annotations

try:
    from config import get_retrieval_bool
except ImportError:
    get_retrieval_bool = lambda k, d=False: d  # type: ignore

from application.rag.proxy_settings_contract import load_proxy_settings, resolve_retrieval_ui_bool

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
    try:
        from infrastructure.database import get_settings_repository

        repo = get_settings_repository()
        proxy_settings = load_proxy_settings(repo)
        value, _source = resolve_retrieval_ui_bool(
            key,
            proxy_settings=proxy_settings,
            yaml_fallback=yaml_fallback,
        )
        return value
    except Exception:
        return get_retrieval_bool(key, yaml_fallback)


__all__ = ["RETRIEVAL_UI_BOOL_KEYS", "retrieval_bool_with_ui_override"]
