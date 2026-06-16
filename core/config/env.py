"""Environment and runtime overrides for ChironAI configuration."""

from __future__ import annotations

import os
from typing import Any, Dict
from urllib.parse import urlparse

from config import loader as _config_loader
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
    _server_cfg,
)


def get_extensions_registry_url() -> str:
    """Return configured extension registry URL/path."""
    return os.getenv(
        "CHIRONAI_EXTENSIONS_REGISTRY_URL",
        str(EXTENSIONS_CONFIG.get("registry_url") or DEFAULT_EXTENSIONS_REGISTRY_URL),
    )


def get_extensions_local_registry_fallback() -> str:
    """Return local extension registry fallback URL/path."""
    return os.getenv(
        "CHIRONAI_EXTENSIONS_LOCAL_REGISTRY_FALLBACK",
        str(EXTENSIONS_CONFIG.get("local_fallback_url") or DEFAULT_EXTENSIONS_LOCAL_REGISTRY_FALLBACK),
    )


def get_extensions_blocklist_url() -> str:
    """Return configured extension emergency blocklist URL/path."""
    return os.getenv(
        "CHIRONAI_EXTENSIONS_BLOCKLIST_URL",
        str(EXTENSIONS_CONFIG.get("blocklist_url") or DEFAULT_EXTENSIONS_REMOTE_BLOCKLIST_URL),
    )


def get_extensions_local_blocklist_fallback() -> str:
    """Return local extension emergency blocklist fallback URL/path."""
    return os.getenv(
        "CHIRONAI_EXTENSIONS_LOCAL_BLOCKLIST_FALLBACK",
        str(EXTENSIONS_CONFIG.get("local_blocklist_fallback_url") or DEFAULT_EXTENSIONS_BLOCKLIST_URL),
    )


def get_github_token() -> str:
    """Return optional GitHub personal access token for authenticated API requests.

    Unauthenticated GitHub API calls are limited to 60 requests per hour per IP.
    Set CHIRONAI_GITHUB_TOKEN (or extensions.github_token in server.yaml) to raise
    this limit to 5000 requests per hour and enable private repository access.
    """
    return os.getenv(
        "CHIRONAI_GITHUB_TOKEN",
        str(EXTENSIONS_CONFIG.get("github_token") or ""),
    )


def get_ollama_chat_url() -> str:
    """Return Ollama chat URL, allowing env override."""
    if _config_loader._rsc is not None:
        try:
            return str(_config_loader._rsc.get_ollama_chat_url())
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
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

    Docker-backed Ollama is owned by the ollama-provider extension; set
    ``OLLAMA_BASE_URL`` / ``OLLAMA_CHAT_URL`` when using a non-default port.
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
    if _config_loader._rsc is not None:
        try:
            return str(_config_loader._rsc.get_ollama_generate_url())
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    return os.getenv(
        "OLLAMA_URL",
        OLLAMA_CONFIG.get("generate_url", "http://localhost:11434/api/generate"),
    )


def get_ollama_embed_url() -> str:
    """Return Ollama embed URL, allowing env override."""
    if _config_loader._rsc is not None:
        try:
            return str(_config_loader._rsc.get_ollama_embed_url())
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    return os.getenv(
        "OLLAMA_EMBED_URL",
        OLLAMA_CONFIG.get("embed_url", "http://localhost:11434/api/embed"),
    )


def get_default_chat_model() -> str:
    """Default chat model id from env/yaml (compat env: ``OLLAMA_CHAT_MODEL``)."""
    return get_ollama_chat_model()


def get_default_embed_model() -> str:
    """Default embed model id from env/yaml (compat env: ``RAG_EMBED_MODEL``)."""
    return get_ollama_embed_model()


def get_default_rerank_model() -> str:
    """Default rerank model id from env/yaml (compat env: ``OLLAMA_RERANK_MODEL``)."""
    return get_ollama_rerank_model()


def get_ollama_chat_model() -> str:
    """Return chat model name, allowing env override. Empty string means 'not configured'."""
    if _config_loader._rsc is not None:
        try:
            return str(_config_loader._rsc.get_ollama_chat_model())
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    env_val = os.getenv("OLLAMA_CHAT_MODEL")
    if env_val is not None:
        return env_val.strip()
    raw = OLLAMA_CONFIG.get("chat_model", "")
    return str(raw).strip()


def get_ollama_embed_model() -> str:
    """Return embed model name (Ollama /api/embed).

    Resolution order (first non-empty wins):
    1. ``RAG_EMBED_MODEL``
    2. ``config/models.yaml`` → ``ollama.embed_model``
    3. ``ollama.embed_model_last_resort`` (YAML only; no Python literal defaults)
    """
    if _config_loader._rsc is not None:
        try:
            return str(_config_loader._rsc.get_ollama_embed_model())
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    env_v = os.getenv("RAG_EMBED_MODEL")
    if env_v is not None and str(env_v).strip() != "":
        return str(env_v).strip()
    yaml_v = OLLAMA_CONFIG.get("embed_model")
    if yaml_v is not None and str(yaml_v).strip() != "":
        return str(yaml_v).strip()
    fb = OLLAMA_CONFIG.get("embed_model_last_resort")
    if fb is not None and str(fb).strip() != "":
        return str(fb).strip()
    return ""


def get_ollama_embed_timeout_seconds() -> float:
    """
    HTTP read timeout for Ollama /api/embed (RAG query + indexing via OllamaEmbeddingProvider).
    Override with OLLAMA_EMBED_TIMEOUT (seconds).
    """
    if _config_loader._rsc is not None:
        try:
            return float(_config_loader._rsc.get_ollama_embed_timeout_seconds())
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
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
    """Return rerank model name (Ollama generate), allowing env override.

    Resolution order (first non-empty wins):
    1. ``OLLAMA_RERANK_MODEL``
    2. ``config/models.yaml`` → ``ollama.rerank_model``
    3. ``config/models.yaml`` -> ``ollama.rerank_model_last_resort`` (no Python literals)

    Empty strings are skipped so ``ollama.rerank_model: ""`` does not yield
    ``model: ""`` (404).
    """
    if _config_loader._rsc is not None:
        try:
            return str(_config_loader._rsc.get_ollama_rerank_model())
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    env_v = os.getenv("OLLAMA_RERANK_MODEL")
    if env_v is not None and str(env_v).strip() != "":
        return str(env_v).strip()
    ollama_v = OLLAMA_CONFIG.get("rerank_model")
    if ollama_v is not None and str(ollama_v).strip() != "":
        return str(ollama_v).strip()
    fb = OLLAMA_CONFIG.get("rerank_model_last_resort")
    if fb is not None and str(fb).strip() != "":
        return str(fb).strip()
    return ""


def get_qdrant_url() -> str:
    """Return Qdrant URL, allowing env override."""
    if _config_loader._rsc is not None:
        try:
            return str(_config_loader._rsc.get_qdrant_url())
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    return os.getenv("QDRANT_URL", QDRANT_CONFIG.get("url", "http://localhost:6333"))


def get_rag_prompt_name() -> str:
    """Return RAG system prompt name (stem of a .md file in prompts/). Override with RAG_PROMPT env."""
    return os.getenv("RAG_PROMPT", RAG_CONFIG.get("prompt", "system_rag_v1"))


_RAG_INT_ENV_KEYS: dict[str, str] = {
    "context_chunk_chars": "RAG_CONTEXT_CHUNK_CHARS",
    "context_total_chars": "RAG_CONTEXT_TOTAL_CHARS",
}


def get_rag_int(key: str, default: int) -> int:
    """Helper to get integer RAG config with default. Env overrides YAML for selected keys."""
    if _config_loader._rsc is not None:
        try:
            return int(_config_loader._rsc.get_rag_int(key, default))
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    env_name = _RAG_INT_ENV_KEYS.get(key)
    if env_name:
        env_v = os.getenv(env_name)
        if env_v is not None and str(env_v).strip() != "":
            try:
                return int(env_v)
            except (TypeError, ValueError):
                pass
    try:
        value = RAG_CONFIG.get(key, default)
        return int(value)
    except (TypeError, ValueError):
        return default


def get_rag_float(key: str, default: float) -> float:
    """Helper to get float RAG config with default."""
    if _config_loader._rsc is not None:
        try:
            return float(_config_loader._rsc.get_rag_float(key, default))
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    try:
        value = RAG_CONFIG.get(key, default)
        return float(value)
    except (TypeError, ValueError):
        return default


def get_proxy_rerank_enabled() -> bool:
    """Return whether rerank is enabled for the proxy (no DB required). Default False."""
    if _config_loader._rsc is not None:
        try:
            return bool(_config_loader._rsc.get_rag_bool("proxy_rerank_enabled", False))
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    return bool(RAG_CONFIG.get("proxy_rerank_enabled", False))


def get_retrieval_int(key: str, default: int) -> int:
    """Helper to get integer retrieval config with default. ``RAG_TOP_K`` overrides ``top_k``."""
    if _config_loader._rsc is not None:
        try:
            return int(_config_loader._rsc.get_retrieval_int(key, default))
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    if key == "top_k":
        env_v = os.getenv("RAG_TOP_K")
        if env_v is not None and str(env_v).strip() != "":
            try:
                return int(env_v)
            except (TypeError, ValueError):
                pass
    try:
        value = RETRIEVAL_CONFIG.get(key, default)
        return int(value)
    except (TypeError, ValueError):
        return default


def get_retrieval_list(key: str, default: list) -> list:
    """Helper to get list retrieval config with default."""
    if _config_loader._rsc is not None:
        try:
            return list(_config_loader._rsc.get_retrieval_list(key, default))
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    value = RETRIEVAL_CONFIG.get(key, default)
    return value if isinstance(value, list) else default


def get_retrieval_dict(key: str, default: dict) -> dict:
    """Helper to get dict retrieval config with default."""
    if _config_loader._rsc is not None:
        try:
            return dict(_config_loader._rsc.get_retrieval_dict(key, default))
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    value = RETRIEVAL_CONFIG.get(key, default)
    return value if isinstance(value, dict) else default


def get_retrieval_bool(key: str, default: bool = False) -> bool:
    """Helper to get boolean retrieval config with default."""
    if _config_loader._rsc is not None:
        try:
            return bool(_config_loader._rsc.get_retrieval_bool(key, default))
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
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
    if _config_loader._rsc is not None:
        try:
            return int(_config_loader._rsc.get_indexing_int(key, default))
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    try:
        value = INDEXING_CONFIG.get(key, default)
        return int(value)
    except (TypeError, ValueError):
        return default


def get_indexing_float(key: str, default: float) -> float:
    """Helper to get float indexing config with default."""
    if _config_loader._rsc is not None:
        try:
            return float(_config_loader._rsc.get_indexing_float(key, default))
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
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
    if _config_loader._rsc is not None:
        try:
            return dict(_config_loader._rsc.get_ollama_chat_options())
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    return OLLAMA_CONFIG.get("chat_options", {
        "num_predict": 3072,
        "temperature": 0.0,
        # Ollama rejects greedy sampling (temperature 0) with top_p < 1.
        "top_p": 1.0,
    })


def get_qdrant_collection_name() -> str:
    """Return Qdrant collection name, allowing env override."""
    if _config_loader._rsc is not None:
        try:
            return os.getenv(
                "QDRANT_COLLECTION_NAME",
                str(_config_loader._rsc.QDRANT_CONFIG.get("collection_name", "webcrawl")),
            )
        except Exception:  # safe: optional runtime settings client; fall back to env defaults
            pass
    return os.getenv(
        "QDRANT_COLLECTION_NAME",
        QDRANT_CONFIG.get("collection_name", "webcrawl")
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


SERVER_PORT_APP_SETTING = "server_port"
SERVER_PORT_LAST_ACTIVE_APP_SETTING = "server_port_last_active"
ACTIVE_SERVER_PORT_ENV = "CHIRONAI_ACTIVE_SERVER_PORT"
DEFAULT_SERVER_PORT = 8080


def _valid_server_port(raw: Any) -> int | None:
    """Return a TCP port in range, or None for invalid input."""
    try:
        port = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if 1 <= port <= 65535:
        return port
    return None


def _get_app_setting_value(key: str, settings_repo: Any | None = None) -> str | None:
    try:
        repo = settings_repo
        if repo is None:
            from infrastructure.database import get_settings_repository  # noqa: PLC0415

            repo = get_settings_repository()
        value = repo.get_app_setting(key)
        return None if value is None else str(value)
    except Exception:  # safe: settings repository optional during bootstrap
        return None


def _resolve_server_port(settings_repo: Any | None = None) -> tuple[int, str]:
    env_port = _valid_server_port(os.getenv("SERVER_PORT"))
    if env_port is not None:
        return env_port, "env"

    settings_port = _valid_server_port(_get_app_setting_value(SERVER_PORT_APP_SETTING, settings_repo))
    if settings_port is not None:
        return settings_port, "settings"

    config_port = _valid_server_port(SERVER_CONFIG.get("port"))
    if config_port is not None:
        return config_port, "config"

    return DEFAULT_SERVER_PORT, "default"


def get_server_port() -> int:
    """Return desired server port: env > app_settings > YAML config > default."""
    port, _source = _resolve_server_port()
    return port


def get_active_server_port(settings_repo: Any | None = None) -> int:
    """Return the port this process should advertise while running."""
    active_port = _valid_server_port(os.getenv(ACTIVE_SERVER_PORT_ENV))
    if active_port is not None:
        return active_port
    return get_server_port_metadata(settings_repo)["server_port"]


def record_active_server_port(port: int, settings_repo: Any | None = None) -> None:
    """Remember the currently bound server port for status URLs and next restart cleanup."""
    valid_port = _valid_server_port(port)
    if valid_port is None:
        return
    os.environ[ACTIVE_SERVER_PORT_ENV] = str(valid_port)
    try:
        repo = settings_repo
        if repo is None:
            from infrastructure.database import get_settings_repository  # noqa: PLC0415

            repo = get_settings_repository()
        repo.set_app_setting(SERVER_PORT_LAST_ACTIVE_APP_SETTING, str(valid_port))
    except Exception:  # safe: persisting active port is best-effort during startup
        pass


def get_server_port_metadata(settings_repo: Any | None = None) -> dict[str, Any]:
    """Return effective, active, and source metadata for the main WebUI/backend port."""
    port, source = _resolve_server_port(settings_repo)
    active_port = _valid_server_port(os.getenv(ACTIVE_SERVER_PORT_ENV)) or port
    return {
        "server_port": port,
        "server_port_active": active_port,
        "server_port_source": source,
        "server_port_restart_required": port != active_port,
    }


def get_server_port_candidate_ports(settings_repo: Any | None = None) -> list[int]:
    """Ports worth stopping before launch: desired, active, previous active, config, default."""
    desired_port = get_server_port_metadata(settings_repo)["server_port"]
    candidates = [
        desired_port,
        _valid_server_port(os.getenv(ACTIVE_SERVER_PORT_ENV)),
        _valid_server_port(_get_app_setting_value(SERVER_PORT_LAST_ACTIVE_APP_SETTING, settings_repo)),
        _valid_server_port(_get_app_setting_value(SERVER_PORT_APP_SETTING, settings_repo)),
        _valid_server_port(SERVER_CONFIG.get("port")),
        DEFAULT_SERVER_PORT,
    ]
    out: list[int] = []
    for port in candidates:
        if port is not None and port not in out:
            out.append(port)
    return out


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


def get_v1_include_autocomplete_logical_model() -> bool:
    """
    When True, GET /v1/models lists ChironAI-Autocomplete when an Ollama autocomplete model is configured,
    in addition to user-defined build ids.
    """
    env = os.getenv("LLM_PROXY_V1_INCLUDE_AUTOCOMPLETE_MODEL", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    return bool(LLM_PROXY_SERVER_CONFIG.get("v1_include_autocomplete_logical_model", True))
