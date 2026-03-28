"""
Configuration loader for ChironAI.

Reads YAML config files from the local `config/` directory and exposes
typed dictionaries with sensible defaults. Environment variables can
override YAML values where appropriate.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - runtime error if dependency missing
    yaml = None  # type: ignore


_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _BASE_DIR / "config"


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
    except Exception:
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


def get_ollama_chat_url() -> str:
    """Return Ollama chat URL, allowing env override."""
    return os.getenv(
        "OLLAMA_CHAT_URL",
        OLLAMA_CONFIG.get("chat_url", "http://localhost:11434/api/chat"),
    )


def get_ollama_base_url() -> str:
    """
    Ollama HTTP API base ``scheme://host:port`` with no path (suitable for ``/api/tags``, etc.).

    Order:
    1. ``OLLAMA_BASE_URL`` if set (trailing ``/api/...`` segments are stripped if present).
    2. Host and port from ``OLLAMA_CHAT_URL`` / ``models.yaml`` ``ollama.chat_url`` (same as RAG/chat).
    3. ``http://localhost:11434`` (standard ``ollama serve`` default).

    Note: ServiceStarter defaults to port 11343 for its Docker stack; WebUI model listing must not
    use that unless you set ``OLLAMA_BASE_URL`` / ``OLLAMA_CHAT_URL`` accordingly.
    """
    api_suffixes = (
        "/api/chat",
        "/api/generate",
        "/api/embed",
        "/api/tags",
        "/api/show",
        "/api/ps",
        "/api/pull",
        "/api/push",
    )

    def _normalize_base(raw: str) -> str | None:
        s = (raw or "").strip().rstrip("/")
        if not s:
            return None
        for suf in api_suffixes:
            if s.endswith(suf):
                s = s[: -len(suf)].rstrip("/")
                break
        if "://" not in s:
            s = f"http://{s}"
        parsed = urlparse(s)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        return None

    from_env = (os.getenv("OLLAMA_BASE_URL") or "").strip()
    if from_env:
        got = _normalize_base(from_env)
        if got:
            return got

    chat = get_ollama_chat_url()
    parsed = urlparse(chat)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return "http://localhost:11434"


def get_ollama_generate_url() -> str:
    """Return Ollama generate URL, allowing env override."""
    return os.getenv(
        "OLLAMA_URL",
        OLLAMA_CONFIG.get("generate_url", "http://localhost:11434/api/generate"),
    )


def get_ollama_embed_url() -> str:
    """Return Ollama embed URL, allowing env override."""
    return os.getenv(
        "OLLAMA_EMBED_URL",
        OLLAMA_CONFIG.get("embed_url", "http://localhost:11434/api/embed"),
    )


def get_ollama_chat_model() -> str:
    """Return chat model name, allowing env override."""
    return os.getenv(
        "OLLAMA_CHAT_MODEL",
        OLLAMA_CONFIG.get(
            "chat_model", "danielsheep/gpt-oss-20b-unsloth:UD-Q6_K_XL"
        ),
    )


def get_ollama_embed_model() -> str:
    """Return embed model name, allowing env override."""
    return os.getenv(
        "RAG_EMBED_MODEL",
        OLLAMA_CONFIG.get("embed_model", "mxbai-embed-large"),
    )


def get_ollama_embed_timeout_seconds() -> float:
    """
    HTTP read timeout for Ollama /api/embed (RAG query + indexing via OllamaEmbeddingProvider).
    Override with OLLAMA_EMBED_TIMEOUT (seconds).
    """
    raw = os.getenv("OLLAMA_EMBED_TIMEOUT")
    if raw is not None and str(raw).strip() != "":
        try:
            return max(10.0, float(raw))
        except (TypeError, ValueError):
            pass
    try:
        v = float(OLLAMA_CONFIG.get("embed_timeout_seconds", 180))
        return max(10.0, v)
    except (TypeError, ValueError):
        return 180.0


def get_ollama_rerank_model() -> str:
    """Return rerank model name (Ollama generate), allowing env override."""
    return os.getenv(
        "OLLAMA_RERANK_MODEL",
        OLLAMA_CONFIG.get("rerank_model", "devstral-ios"),
    )


def get_qdrant_url() -> str:
    """Return Qdrant URL, allowing env override."""
    return os.getenv("QDRANT_URL", QDRANT_CONFIG.get("url", "http://localhost:6333"))


def get_rag_prompt_name() -> str:
    """Return RAG system prompt name (stem of a .md file in prompts/). Override with RAG_PROMPT env."""
    return os.getenv("RAG_PROMPT", RAG_CONFIG.get("prompt", "system_rag_v1"))


def get_rag_int(key: str, default: int) -> int:
    """Helper to get integer RAG config with default."""
    try:
        value = RAG_CONFIG.get(key, default)
        return int(value)
    except (TypeError, ValueError):
        return default


def get_rag_float(key: str, default: float) -> float:
    """Helper to get float RAG config with default."""
    try:
        value = RAG_CONFIG.get(key, default)
        return float(value)
    except (TypeError, ValueError):
        return default


def get_proxy_rerank_enabled() -> bool:
    """Return whether rerank is enabled for the proxy (no DB required). Default False."""
    return bool(RAG_CONFIG.get("proxy_rerank_enabled", False))


def get_retrieval_int(key: str, default: int) -> int:
    """Helper to get integer retrieval config with default."""
    try:
        value = RETRIEVAL_CONFIG.get(key, default)
        return int(value)
    except (TypeError, ValueError):
        return default


def get_retrieval_list(key: str, default: list) -> list:
    """Helper to get list retrieval config with default."""
    value = RETRIEVAL_CONFIG.get(key, default)
    return value if isinstance(value, list) else default


def get_retrieval_dict(key: str, default: dict) -> dict:
    """Helper to get dict retrieval config with default."""
    value = RETRIEVAL_CONFIG.get(key, default)
    return value if isinstance(value, dict) else default


def get_retrieval_bool(key: str, default: bool = False) -> bool:
    """Helper to get boolean retrieval config with default."""
    value = RETRIEVAL_CONFIG.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value) if value is not None else default


def get_crawler_int(key: str, default: int) -> int:
    """Helper to get integer crawler config with default."""
    try:
        value = CRAWLER_CONFIG.get(key, default)
        return int(value)
    except (TypeError, ValueError):
        return default


def get_crawler_list(key: str, default: list) -> list:
    """Helper to get list crawler config with default."""
    value = CRAWLER_CONFIG.get(key, default)
    return value if isinstance(value, list) else default


def get_indexing_int(key: str, default: int) -> int:
    """Helper to get integer indexing config with default."""
    try:
        value = INDEXING_CONFIG.get(key, default)
        return int(value)
    except (TypeError, ValueError):
        return default


def get_indexing_float(key: str, default: float) -> float:
    """Helper to get float indexing config with default."""
    try:
        value = INDEXING_CONFIG.get(key, default)
        return float(value)
    except (TypeError, ValueError):
        return default


def get_indexing_list(key: str, default: list) -> list:
    """Helper to get list indexing config with default."""
    value = INDEXING_CONFIG.get(key, default)
    return value if isinstance(value, list) else default


def get_indexing_dict(key: str, default: dict) -> dict:
    """Helper to get dict indexing config with default."""
    value = INDEXING_CONFIG.get(key, default)
    return value if isinstance(value, dict) else default


def get_ollama_chat_options() -> Dict[str, Any]:
    """Return Ollama chat generation options from config."""
    return OLLAMA_CONFIG.get("chat_options", {
        "num_predict": 3072,
        "temperature": 0.0,
        "top_p": 0.1,
    })


def get_qdrant_collection_name() -> str:
    """Return Qdrant collection name, allowing env override."""
    return os.getenv(
        "QDRANT_COLLECTION_NAME",
        QDRANT_CONFIG.get("collection_name", "dev_docs")
    )


def get_framework_collection_ttl_days() -> int:
    """Default TTL in days for framework collections; after this they are considered stale. Overridable via app_settings key framework_collection_ttl_days."""
    try:
        return int(os.getenv("FRAMEWORK_COLLECTION_TTL_DAYS", RAG_CONFIG.get("framework_collection_ttl_days", 90)))
    except (TypeError, ValueError):
        return 90


def get_default_rag_top_k() -> int:
    """Default top_k for RAG when not overridden per collection. Overridable via app_settings key default_rag_top_k."""
    try:
        return int(os.getenv("DEFAULT_RAG_TOP_K", RAG_CONFIG.get("default_rag_top_k", 4)))
    except (TypeError, ValueError):
        return 4


def get_server_host() -> str:
    """Return server bind host, allowing env override."""
    return os.getenv("SERVER_HOST", SERVER_CONFIG.get("host", "0.0.0.0"))


def get_server_port() -> int:
    """Return server port, allowing env override."""
    try:
        port = os.getenv("SERVER_PORT")
        if port:
            return int(port)
    except (TypeError, ValueError):
        pass
    return int(SERVER_CONFIG.get("port", 8080))


def get_webui_port() -> int:
    """Return WebUI Flask app port (tmrag start), allowing env override."""
    try:
        port = os.getenv("WEBUI_PORT")
        if port:
            return int(port)
    except (TypeError, ValueError):
        pass
    _webui_cfg = _server_cfg.get("webui", {})
    return int(_webui_cfg.get("port", 5000))


def get_log_level() -> int:
    """Return logging level (e.g. logging.INFO). Env LOG_LEVEL overrides config."""
    name = os.getenv("LOG_LEVEL", _server_cfg.get("logging", {}).get("level", "INFO"))
    return getattr(__import__("logging"), name.upper(), 20)  # 20 = INFO

