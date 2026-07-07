"""WebUI-facing RAG retrieval settings helpers owned by the application layer."""

from __future__ import annotations

from typing import Any

try:
    from config import get_retrieval_int
except ImportError:
    get_retrieval_int = lambda _key, default=0: default  # type: ignore[assignment,misc]

RAG_TRIGGER_HELP_ROWS: list[dict[str, str]] = [
    {"signal": "Keyword (from collections or config)", "points": "+3"},
    {"signal": "CamelCase (e.g. SwiftUI, URLSession)", "points": "+2"},
    {"signal": "Code block (```)", "points": "+4"},
    {"signal": "Code keyword (func, class, struct, let, var…)", "points": "+4"},
    {"signal": "API signature name(...)", "points": "+2"},
    {"signal": "File extension (.swift, .py…)", "points": "+2"},
    {"signal": "snake_case (e.g. load_data)", "points": "+1"},
    {"signal": "Strong technical phrase (error, API, framework…)", "points": "+2"},
    {"signal": "Weak technical phrase (how does, best practice…)", "points": "+1"},
]


def get_effective_rag_trigger_threshold(settings_repo: Any | None = None) -> int:
    """Return persisted WebUI threshold or config default."""
    try:
        repo = settings_repo
        if repo is None:
            from infrastructure.database import get_settings_repository

            repo = get_settings_repository()
        raw = repo.get_app_setting("rag_trigger_threshold")
        if raw is not None and str(raw).strip() != "":
            return int(raw)
    except Exception:  # safe: app setting override optional; use config default
        pass
    return get_retrieval_int("rag_trigger_threshold", 2)


def get_rag_required_keywords_from_module(keyword_collections_repository_factory: Any | None) -> list[str] | None:
    """Return enabled keyword-collection terms when the repository is available."""
    if keyword_collections_repository_factory is None:
        return None
    try:
        repo = keyword_collections_repository_factory()
        flat = repo.get_enabled_keywords_flat()
        return flat if flat else None
    except Exception:
        return None


def config_default_chat_model() -> str:
    try:
        from config import get_default_chat_model

        return str(get_default_chat_model() or "").strip()
    except Exception:
        return ""


def config_default_embed_model() -> str:
    try:
        from config import get_default_embed_model

        return str(get_default_embed_model() or "").strip()
    except Exception:
        return ""


def config_default_rerank_model() -> str:
    try:
        from config import get_default_rerank_model

        return str(get_default_rerank_model() or "").strip()
    except Exception:
        return ""


__all__ = [
    "RAG_TRIGGER_HELP_ROWS",
    "config_default_chat_model",
    "config_default_embed_model",
    "config_default_rerank_model",
    "get_effective_rag_trigger_threshold",
    "get_rag_required_keywords_from_module",
]
