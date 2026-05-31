"""Pure helpers extracted from chat_completions_handler (low-risk, testable)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from application.rag.proxy_settings_contract import load_proxy_settings
from llm_proxy.chat_completions_ollama_proxy import gpt_oss_model_requires_reasoning_level
from llm_proxy.pipeline_steps import get_proxy_pipeline_step_meta

_RAG_LOG = logging.getLogger("llm_proxy")


def build_forced_think_value(
    *,
    body: dict[str, Any],
    active_build: dict[str, Any] | None,
    model_name: str | None,
) -> bool | str | None:
    if not isinstance(active_build, dict) or "think" in body:
        return None
    if gpt_oss_model_requires_reasoning_level(model_name):
        if active_build.get("chat_think"):
            level = str(
                body.get("reasoning_level")
                or body.get("reasoning")
                or active_build.get("reasoning_level")
                or ""
            ).strip().lower()
            return level if level in {"low", "medium", "high"} else "medium"
        return None
    return True if active_build.get("chat_think") else False


def log_rag_error(stage: str, error: Exception) -> None:
    _RAG_LOG.error("RAG stage=%s | %s: %s", stage, type(error).__name__, error)


def log_rag_error_private(stage: str, error: Exception, *, private_build: bool) -> None:
    if private_build:
        _RAG_LOG.error("RAG stage=%s | %s", stage, type(error).__name__)
    else:
        log_rag_error(stage, error)


def append_pipeline_step_trace(
    trace: dict[str, Any],
    *,
    step_id: str,
    status: str,
    reason: str | None = None,
) -> None:
    meta = get_proxy_pipeline_step_meta(step_id) or {
        "id": step_id,
        "icon": "",
        "title": step_id,
        "description": "",
    }
    trace.setdefault("pipeline_steps", [])
    trace["pipeline_steps"].append(
        {
            "id": meta["id"],
            "icon": meta["icon"],
            "title": meta["title"],
            "description": meta["description"],
            "status": status,
            "reason": reason,
        }
    )


def load_proxy_settings_and_model(get_settings_repository: Any) -> tuple[dict[str, object], str]:
    """Load proxy_settings JSON + proxy_model with backward-compatible fallback to settings.model."""
    proxy_settings: dict[str, object] = {}
    proxy_model_setting = ""
    try:
        settings_repo = get_settings_repository()
        proxy_model_setting = (settings_repo.get_app_setting("proxy_model") or "").strip()
        proxy_settings = load_proxy_settings(settings_repo)
    except Exception:
        pass
    if not proxy_model_setting and proxy_settings.get("model"):
        proxy_model_setting = str(proxy_settings.get("model") or "").strip()
    return proxy_settings, proxy_model_setting


def apply_selected_rerank_model(
    rerank_client: Any,
    proxy_settings: dict[str, object],
    trace: dict[str, Any],
) -> Any:
    selected = str(proxy_settings.get("rerank_model") or "").strip()
    if not selected or rerank_client is None:
        return rerank_client

    current = str(
        getattr(rerank_client, "_model", None)
        or getattr(rerank_client, "model", None)
        or ""
    ).strip()
    if hasattr(rerank_client, "_model"):
        setattr(rerank_client, "_model", selected)
    elif hasattr(rerank_client, "model"):
        setattr(rerank_client, "model", selected)
    else:
        return rerank_client

    req_trace = trace.setdefault("request", {})
    req_trace["rerank_model"] = selected
    req_trace["rerank_model_source"] = "proxy_settings.rerank_model"
    if selected != current:
        req_trace["rerank_model_override"] = selected
    return rerank_client


def web_supplement_used_from_trace(trace: dict[str, Any]) -> bool:
    internet = trace.get("internet")
    if not isinstance(internet, dict):
        return False
    if internet.get("used") is True:
        return True
    ws = internet.get("web_supplement")
    if isinstance(ws, dict) and ws.get("used") is True:
        return True
    return False


def rag_request_completed_payload(
    *,
    user_query: str,
    trace_id: str,
    use_model: str,
    requested_model: str,
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    rag_context_for_obs: Any,
    rag_timings: dict[str, float] | None,
    trace: dict[str, Any],
    stream: bool,
    is_autocomplete: bool,
    native_tools: bool = False,
) -> dict[str, Any]:
    """Single structured log line per completed proxy request (Loki/ELK friendly)."""
    query_hash = hashlib.sha256((user_query or "").encode()).hexdigest()[:16]
    chunks_count = len(rag_context_for_obs.chunks_info) if rag_context_for_obs else 0
    max_score = float(rag_context_for_obs.max_score) if rag_context_for_obs else 0.0
    rag_quality = getattr(rag_context_for_obs, "rag_quality", None)
    cov_rep = getattr(rag_context_for_obs, "coverage_report", None)
    out: dict[str, Any] = {
        "event": "rag_request_completed",
        "query_hash": query_hash,
        "trace_id": trace_id,
        "model": use_model,
        "requested_model": requested_model,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "chunks_count": chunks_count,
        "max_score": max_score,
        "is_autocomplete": is_autocomplete,
        "stream": stream,
        "native_tools": native_tools,
        "rag_steps": dict(rag_timings or {}),
        "web_supplement_used": web_supplement_used_from_trace(trace),
    }
    if isinstance(rag_quality, dict):
        out["rag_quality"] = rag_quality
    if isinstance(cov_rep, dict):
        out["coverage_ratio"] = cov_rep.get("coverage_ratio")
    return out
