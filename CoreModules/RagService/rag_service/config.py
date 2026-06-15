"""
Standalone configuration helpers for rag_service.

Configuration sources, in order:
1. Environment variables.
2. Optional YAML file path from ``RAG_SERVICE_CONFIG``.
3. Built-in defaults.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_RETRIEVAL: dict[str, Any] = {
    "max_embed_text_length": 400,
    "top_k": 8,
    "multi_chunk_top_k": 16,
    "multi_chunk_final_k": 8,
    "rerank_max_candidates": 12,
    "final_context_k": 4,
    "coverage_aware_selection": False,
    "coverage_extra_terms": [],
    "coverage_gate_enabled": False,
    "coverage_gate_min_percent": 75,
    "coverage_gate_boost_final_k": 2,
    "coverage_gate_max_final_k": 12,
    "coverage_retry_supplemental_search_enabled": False,
    "coverage_retry_top_k": 6,
    "coverage_retry_max_missing_terms": 8,
    "coverage_retry_final_k": 0,
    "structured_rag_context_enabled": False,
    "concept_expansion_enabled": False,
    "concept_expansion_seed_hits": 4,
    "concept_expansion_max_terms": 16,
    "concept_expansion_pass2_top_k": 8,
    "concept_expansion_map": {
        "actor": "Sendable nonisolated MainActor isolated global actor",
        "task": "async await cancellation TaskGroup Task",
        "sendable": "isolated concurrency actor @unchecked",
        "mainactor": "MainActor UI thread dispatchQueue",
    },
    "doc_type_preferred_for_qa": ["conceptual", "overview", "tutorial", "documentation", "howto"],
    "doc_type_weight": {
        "conceptual": 3,
        "overview": 2,
        "tutorial": 1,
        "documentation": 1,
        "howto": 1,
        "release_notes": -2,
        "news": -2,
    },
    "doc_scope_preferred_for_qa": ["api_symbol", "guide", "tutorial"],
    "doc_scope_weight": {
        "api_symbol": 2,
        "guide": 1,
        "tutorial": 1,
        "discussion": 0,
        "articles": 0,
        "books": 0,
        "forums": -1,
    },
    "multi_chunk_keywords": [
        "compare",
        "comparison",
        "difference",
        "explain fully",
        "fully explain",
        "lifecycle",
        "all ways",
        "all options",
        "list all",
        "step by step",
        "overview of",
    ],
    "retrieval_stop_words": [
        "please",
        "can you",
        "could you",
        "would you",
        "tell me",
        "explain",
        "show me",
        "give me",
        "how to",
        "how do",
        "what is",
        "what are",
    ],
    "skip_rag_greetings": ["hi", "hello", "hey", "good morning", "good evening"],
    "skip_rag_greeting_max_length": 30,
    "rag_trigger_threshold": 2,
    "rag_trigger_technical_phrases_strong": [
        "compile",
        "runtime",
        "API",
        "framework",
        "syntax",
        "deprecated",
        "migration",
        "error",
        "bug",
        "architecture",
    ],
    "rag_trigger_technical_phrases_weak": [
        "how does",
        "best practice",
        "pattern",
        "algorithm",
        "refactor",
        "unit test",
        "dependency",
        "library",
        "integration test",
    ],
    "rag_required_keywords": [
        "swift",
        "swiftui",
        "uikit",
        "objective-c",
        "objc",
        "xcode",
        "ios",
        "macos",
        "combine",
        "cocoa",
        "appkit",
        "watchos",
        "tvos",
        "uiviewcontroller",
        "view model",
        "project",
        "codebase",
        "repository",
        "our code",
        "analyze",
        "review this code",
        "explain this code",
        "code snippet",
        "observation",
        "observable",
        "observation tracking",
    ],
    "rerank_model": "",
    "hybrid_sparse_enabled": True,
    "query_expansion_enabled": False,
    "query_expansion_max_variants": 3,
    "query_expansion_abbreviations": {
        "MVVM": "Model View ViewModel",
        "@Observable": "Observable macro Swift Observation",
        "UIKit": "UIKit framework",
        "SwiftUI": "SwiftUI framework",
    },
    "concept_aliases": {
        "observable macro": " observation tracking observation framework updating views automatically with observation tracking ",
        "observable": " observation tracking observation framework ",
        "observation tracking": " observation tracking observation framework ",
    },
}

_DEFAULT_INDEXING: dict[str, Any] = {
    "chunk_max_size": 1200,
    "chunk_min_size": 300,
    "chunk_overlap": 0,
    "min_chunk_words": 5,
    "min_chunk_alpha_ratio": 0.2,
}

_DEFAULT_RAG: dict[str, Any] = {
    "context_chunk_chars": 1000,
    "context_total_chars": 7000,
    "confidence_threshold": 0.75,
    "log_preview_chars": 800,
}

_DEFAULT_OLLAMA: dict[str, Any] = {
    "chat_url": "http://localhost:11434/api/chat",
    "generate_url": "http://localhost:11434/api/generate",
    "embed_url": "http://localhost:11434/api/embed",
    "chat_model": "",
    "embed_model": "",
    "rerank_model": "",
    "embed_timeout_seconds": 180.0,
    "chat_options": {"num_predict": 3072, "temperature": 0.0, "top_p": 1.0},
}

_DEFAULT_QDRANT: dict[str, Any] = {
    "url": "http://localhost:6333",
    "collection_name": "webcrawl",
}

_DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "default": {
        "prefix": "You are RAG Beta 0.1, a standalone retrieval-augmented assistant.",
        "suffix": "If retrieved evidence is insufficient, say so clearly.",
    }
}

_retrieval_overrides_var: ContextVar[dict[str, Any] | None] = ContextVar(
    "rag_service_retrieval_overrides",
    default=None,
)


def _merge_dict(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _merge_dict(dst[key], value)
        else:
            dst[key] = value
    return dst


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _repo_root_guess() -> Path | None:
    """
    Best-effort monorepo root for local/dev runs.

    .../CoreModules/RagService/rag_service/config.py -> repo root is parents[3].
    """
    try:
        return Path(__file__).resolve().parents[3]
    except Exception:
        return None


def _load_host_repo_overlay() -> dict[str, Any]:
    """
    Overlay from project-wide config/*.yaml to avoid silent drift vs proxy/tester.

    Applies only when running inside the monorepo and RAG_SERVICE_CONFIG is not set.
    """
    root = _repo_root_guess()
    if root is None:
        return {}
    cfg_dir = root / "config"
    if not cfg_dir.is_dir():
        return {}

    retrieval = (_load_yaml_file(cfg_dir / "retrieval.yaml").get("retrieval") or {})
    indexing = (_load_yaml_file(cfg_dir / "indexing.yaml").get("indexing") or {})
    rag = (_load_yaml_file(cfg_dir / "rag.yaml").get("rag") or {})
    models = (_load_yaml_file(cfg_dir / "models.yaml").get("ollama") or {})
    server = _load_yaml_file(cfg_dir / "server.yaml")
    qdrant = (server.get("qdrant") or {}) if isinstance(server, dict) else {}

    out: dict[str, Any] = {}
    if isinstance(retrieval, dict):
        out["retrieval"] = retrieval
    if isinstance(indexing, dict):
        out["indexing"] = indexing
    if isinstance(rag, dict):
        out["rag"] = rag
    if isinstance(models, dict):
        out["ollama"] = models
    if isinstance(qdrant, dict):
        out["qdrant"] = qdrant
    return out


@lru_cache(maxsize=1)
def _config_data() -> dict[str, Any]:
    data: dict[str, Any] = {
        "retrieval": dict(_DEFAULT_RETRIEVAL),
        "indexing": dict(_DEFAULT_INDEXING),
        "rag": dict(_DEFAULT_RAG),
        "ollama": dict(_DEFAULT_OLLAMA),
        "qdrant": dict(_DEFAULT_QDRANT),
        "prompts": dict(_DEFAULT_PROMPTS),
    }
    cfg_path = (os.getenv("RAG_SERVICE_CONFIG") or "").strip()
    if cfg_path:
        path = Path(cfg_path)
        if path.is_file():
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                _merge_dict(data, raw)
    else:
        _merge_dict(data, _load_host_repo_overlay())
    return data


def _section(name: str) -> dict[str, Any]:
    value = _config_data().get(name) or {}
    return value if isinstance(value, dict) else {}


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _bool_env(name: str) -> bool | None:
    value = _env(name)
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "on"}


def _retrieval_override_value(key: str) -> Any:
    overrides = _retrieval_overrides_var.get() or {}
    return overrides.get(key)


@contextmanager
def override_retrieval_settings(overrides: dict[str, Any] | None):
    current = dict(_retrieval_overrides_var.get() or {})
    merged = dict(current)
    for key, value in (overrides or {}).items():
        merged[str(key)] = value
    token = _retrieval_overrides_var.set(merged)
    try:
        yield
    finally:
        _retrieval_overrides_var.reset(token)


def get_retrieval_int(key: str, default: int) -> int:
    override = _retrieval_override_value(key)
    if override is not None:
        try:
            return int(override)
        except (TypeError, ValueError):
            return default
    raw = _env(f"RAG_RETRIEVAL_{key.upper()}")
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            return default
    try:
        return int(_section("retrieval").get(key, default))
    except (TypeError, ValueError):
        return default


def get_retrieval_bool(key: str, default: bool = False) -> bool:
    override = _retrieval_override_value(key)
    if override is not None:
        if isinstance(override, bool):
            return override
        if isinstance(override, str):
            return override.strip().lower() in {"1", "true", "yes", "on"}
        return bool(override)
    raw = _bool_env(f"RAG_RETRIEVAL_{key.upper()}")
    if raw is not None:
        return raw
    return bool(_section("retrieval").get(key, default))


def get_retrieval_list(key: str, default: list[Any]) -> list[Any]:
    value = _section("retrieval").get(key, default)
    return list(value) if isinstance(value, list) else list(default)


def get_retrieval_dict(key: str, default: dict[str, Any]) -> dict[str, Any]:
    value = _section("retrieval").get(key, default)
    return dict(value) if isinstance(value, dict) else dict(default)


def get_indexing_int(key: str, default: int) -> int:
    raw = _env(f"RAG_INDEXING_{key.upper()}")
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            return default
    try:
        return int(_section("indexing").get(key, default))
    except (TypeError, ValueError):
        return default


def get_indexing_float(key: str, default: float) -> float:
    raw = _env(f"RAG_INDEXING_{key.upper()}")
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            return default
    try:
        return float(_section("indexing").get(key, default))
    except (TypeError, ValueError):
        return default


def get_rag_int(key: str, default: int) -> int:
    raw = _env(f"RAG_{key.upper()}")
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            return default
    try:
        return int(_section("rag").get(key, default))
    except (TypeError, ValueError):
        return default


def get_rag_float(key: str, default: float) -> float:
    raw = _env(f"RAG_{key.upper()}")
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            return default
    try:
        return float(_section("rag").get(key, default))
    except (TypeError, ValueError):
        return default


def get_rag_bool(key: str, default: bool = False) -> bool:
    raw = _bool_env(f"RAG_{key.upper()}")
    if raw is not None:
        return raw
    value = _section("rag").get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value) if value is not None else default


def get_ollama_chat_url() -> str:
    return _env("OLLAMA_CHAT_URL") or str(_section("ollama").get("chat_url", _DEFAULT_OLLAMA["chat_url"]))


def get_ollama_generate_url() -> str:
    return _env("OLLAMA_GENERATE_URL") or str(_section("ollama").get("generate_url", _DEFAULT_OLLAMA["generate_url"]))


def get_ollama_embed_url() -> str:
    return _env("OLLAMA_EMBED_URL") or str(_section("ollama").get("embed_url", _DEFAULT_OLLAMA["embed_url"]))


def get_default_chat_model() -> str:
    return get_ollama_chat_model()


def get_default_embed_model() -> str:
    return get_ollama_embed_model()


def get_default_rerank_model() -> str:
    return get_ollama_rerank_model()


def get_ollama_chat_model() -> str:
    return _env("OLLAMA_CHAT_MODEL") or str(_section("ollama").get("chat_model", ""))


def get_ollama_embed_model() -> str:
    return _env("OLLAMA_EMBED_MODEL") or str(_section("ollama").get("embed_model", ""))


def get_ollama_rerank_model() -> str:
    env_value = _env("OLLAMA_RERANK_MODEL")
    if env_value:
        return env_value
    ollama_value = str(_section("ollama").get("rerank_model", "") or "").strip()
    if ollama_value:
        return ollama_value
    return str(_section("ollama").get("rerank_model_last_resort", "") or "").strip()


def get_ollama_embed_timeout_seconds() -> float:
    raw = _env("OLLAMA_EMBED_TIMEOUT_SECONDS")
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            return float(_DEFAULT_OLLAMA["embed_timeout_seconds"])
    try:
        return float(_section("ollama").get("embed_timeout_seconds", _DEFAULT_OLLAMA["embed_timeout_seconds"]))
    except (TypeError, ValueError):
        return float(_DEFAULT_OLLAMA["embed_timeout_seconds"])


def get_ollama_chat_options() -> dict[str, Any]:
    value = _section("ollama").get("chat_options", _DEFAULT_OLLAMA["chat_options"])
    return dict(value) if isinstance(value, dict) else dict(_DEFAULT_OLLAMA["chat_options"])


def get_qdrant_url() -> str:
    return _env("QDRANT_URL") or str(_section("qdrant").get("url", _DEFAULT_QDRANT["url"]))


QDRANT_CONFIG: dict[str, Any] = {"collection_name": _section("qdrant").get("collection_name", "webcrawl")}


def get_rag_system_prompt(prompt_name: str | None = None) -> tuple[str, str]:
    prompts = _section("prompts")
    name = (prompt_name or "default").strip() or "default"
    selected = prompts.get(name) or prompts.get("default") or {}
    if not isinstance(selected, dict):
        selected = _DEFAULT_PROMPTS["default"]
    prefix = str(selected.get("prefix", _DEFAULT_PROMPTS["default"]["prefix"]))
    suffix = str(selected.get("suffix", _DEFAULT_PROMPTS["default"]["suffix"]))
    return prefix, suffix
