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
except Exception:
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
BUILD_PROXY_CONFIG: Dict[str, Any] = _server_cfg.get("build_proxy", {})
LLM_PROXY_SERVER_CONFIG: Dict[str, Any] = _server_cfg.get("llm_proxy", {})


def get_ollama_chat_url() -> str:
    """Return Ollama chat URL, allowing env override."""
    if _rsc is not None:
        try:
            return str(_rsc.get_ollama_chat_url())
        except Exception:
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
    if _rsc is not None:
        try:
            return str(_rsc.get_ollama_generate_url())
        except Exception:
            pass
    return os.getenv(
        "OLLAMA_URL",
        OLLAMA_CONFIG.get("generate_url", "http://localhost:11434/api/generate"),
    )


def get_ollama_embed_url() -> str:
    """Return Ollama embed URL, allowing env override."""
    if _rsc is not None:
        try:
            return str(_rsc.get_ollama_embed_url())
        except Exception:
            pass
    return os.getenv(
        "OLLAMA_EMBED_URL",
        OLLAMA_CONFIG.get("embed_url", "http://localhost:11434/api/embed"),
    )


def get_ollama_chat_model() -> str:
    """Return chat model name, allowing env override. Empty string means 'not configured'."""
    if _rsc is not None:
        try:
            return str(_rsc.get_ollama_chat_model())
        except Exception:
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
    if _rsc is not None:
        try:
            return str(_rsc.get_ollama_embed_model())
        except Exception:
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
    if _rsc is not None:
        try:
            return float(_rsc.get_ollama_embed_timeout_seconds())
        except Exception:
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
    if _rsc is not None:
        try:
            return str(_rsc.get_ollama_rerank_model())
        except Exception:
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
    if _rsc is not None:
        try:
            return str(_rsc.get_qdrant_url())
        except Exception:
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
    if _rsc is not None:
        try:
            return int(_rsc.get_rag_int(key, default))
        except Exception:
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
    if _rsc is not None:
        try:
            return float(_rsc.get_rag_float(key, default))
        except Exception:
            pass
    try:
        value = RAG_CONFIG.get(key, default)
        return float(value)
    except (TypeError, ValueError):
        return default


def get_proxy_rerank_enabled() -> bool:
    """Return whether rerank is enabled for the proxy (no DB required). Default False."""
    if _rsc is not None:
        try:
            return bool(_rsc.get_rag_bool("proxy_rerank_enabled", False))
        except Exception:
            pass
    return bool(RAG_CONFIG.get("proxy_rerank_enabled", False))


def get_retrieval_int(key: str, default: int) -> int:
    """Helper to get integer retrieval config with default. ``RAG_TOP_K`` overrides ``top_k``."""
    if _rsc is not None:
        try:
            return int(_rsc.get_retrieval_int(key, default))
        except Exception:
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
    if _rsc is not None:
        try:
            return list(_rsc.get_retrieval_list(key, default))
        except Exception:
            pass
    value = RETRIEVAL_CONFIG.get(key, default)
    return value if isinstance(value, list) else default


def get_retrieval_dict(key: str, default: dict) -> dict:
    """Helper to get dict retrieval config with default."""
    if _rsc is not None:
        try:
            return dict(_rsc.get_retrieval_dict(key, default))
        except Exception:
            pass
    value = RETRIEVAL_CONFIG.get(key, default)
    return value if isinstance(value, dict) else default


def get_retrieval_bool(key: str, default: bool = False) -> bool:
    """Helper to get boolean retrieval config with default."""
    if _rsc is not None:
        try:
            return bool(_rsc.get_retrieval_bool(key, default))
        except Exception:
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
    if _rsc is not None:
        try:
            return int(_rsc.get_indexing_int(key, default))
        except Exception:
            pass
    try:
        value = INDEXING_CONFIG.get(key, default)
        return int(value)
    except (TypeError, ValueError):
        return default


def get_indexing_float(key: str, default: float) -> float:
    """Helper to get float indexing config with default."""
    if _rsc is not None:
        try:
            return float(_rsc.get_indexing_float(key, default))
        except Exception:
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
    if _rsc is not None:
        try:
            return dict(_rsc.get_ollama_chat_options())
        except Exception:
            pass
    return OLLAMA_CONFIG.get("chat_options", {
        "num_predict": 3072,
        "temperature": 0.0,
        # Ollama rejects greedy sampling (temperature 0) with top_p < 1.
        "top_p": 1.0,
    })


def get_qdrant_collection_name() -> str:
    """Return Qdrant collection name, allowing env override."""
    if _rsc is not None:
        try:
            return os.getenv(
                "QDRANT_COLLECTION_NAME",
                str(_rsc.QDRANT_CONFIG.get("collection_name", "webcrawl")),
            )
        except Exception:
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


def get_build_proxy_enabled() -> bool:
    """Second OpenAI /v1 listener for LLM Proxy builds. ``BUILD_PROXY_ENABLED=0`` disables."""
    env = os.getenv("BUILD_PROXY_ENABLED", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    return bool(BUILD_PROXY_CONFIG.get("enabled", True))


def get_build_proxy_host() -> str:
    return os.getenv("BUILD_PROXY_HOST", str(BUILD_PROXY_CONFIG.get("host", "0.0.0.0")))


def get_build_proxy_port() -> int:
    try:
        p = os.getenv("BUILD_PROXY_PORT")
        if p:
            return int(p)
    except (TypeError, ValueError):
        pass
    try:
        return int(BUILD_PROXY_CONFIG.get("port", 8087))
    except (TypeError, ValueError):
        return 8087


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

