"""OpenAI /v1/chat/completions handler."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import base64
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from infrastructure.ollama.gemini_model_id import is_gemini_family_model_name

try:
    from chironai_rag.consumers import RAG_COLLECTION_APP_SETTING
except ImportError:
    RAG_COLLECTION_APP_SETTING = "rag_collection"

from flask import Response, jsonify, request
from api.http.proxy_trace import set_response_artifacts

from infrastructure.metrics import increment, histogram, gauge
from application.rag.proxy_settings_contract import (
    load_proxy_settings,
    resolve_fetch_web_knowledge,
    resolve_rag_collection,
)

from infrastructure.ollama.model_capabilities import (
    caps_supports_thinking,
    caps_supports_tools,
    chat_error_suggests_no_think,
    chat_error_suggests_no_tools,
    get_cached_ollama_capabilities,
)
from infrastructure.ollama.openai_multipart_vision import (
    openai_parts_to_flat_text,
    promote_inline_data_image_urls_in_content,
    sanitize_openai_text_part,
    sanitize_proxy_content_parts,
    VISION_MAX_DECODED_BYTES,
)
from infrastructure.ollama.openai_ollama_tool_bridge import (
    ollama_chat_tool_choice_payload_value,
    openai_finish_reason_from_ollama,
    openai_tool_choice_means_none,
)
from llm_proxy.contracts import LlmProxyWiring
from llm_proxy.pipeline_steps import get_proxy_pipeline_step_meta
from llm_proxy.pipeline_steps.merged_docs_step import run_merged_docs_step
from llm_proxy.pipeline_steps.web_supplement_step import (
    run_web_supplement_step,
)
from llm_proxy.tool_helpers import (
    _build_tool_arguments,
    _build_tool_json_instruction,
    _client_files_snippet,
    _client_selection_snippet,
    _extract_edit_from_response,
    _extract_file_path_from_user_text,
    _extract_line_span_from_user_text,
    _extract_tool_name,
    _get_tool_by_name,
    _select_edit_tool_name,
    _tool_args_have_substantive_body,
    _tool_result_looks_like_unintended_deletion,
    _tool_schema_accepts_content,
    _workspace_doc_refactor_intent,
    _workspace_selection_snippet,
)

_RAG_LOG = logging.getLogger("llm_proxy")


from infrastructure.ollama.model_brand import resolve_brand_key


def _log_rag_error(stage: str, error: Exception) -> None:
    _RAG_LOG.error("RAG stage=%s | %s: %s", stage, type(error).__name__, error)


def _log_rag_error_private(stage: str, error: Exception, *, private_build: bool) -> None:
    if private_build:
        _RAG_LOG.error("RAG stage=%s | %s", stage, type(error).__name__)
    else:
        _log_rag_error(stage, error)


def _append_pipeline_step_trace(
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


def _proxy_settings_optional_int(
    ps: dict[str, Any], key: str, lo: int, hi: int
) -> int | None:
    if not isinstance(ps, dict):
        return None
    raw = ps.get(key)
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    if n < lo or n > hi:
        return None
    return n


def _load_proxy_settings_and_model(get_settings_repository: Any) -> tuple[dict[str, object], str]:
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


def _apply_selected_rerank_model(
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


def _web_supplement_used_from_trace(trace: dict[str, Any]) -> bool:
    internet = trace.get("internet")
    if not isinstance(internet, dict):
        return False
    if internet.get("used") is True:
        return True
    ws = internet.get("web_supplement")
    if isinstance(ws, dict) and ws.get("used") is True:
        return True
    return False


def _rag_request_completed_payload(
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
        "web_supplement_used": _web_supplement_used_from_trace(trace),
    }
    if isinstance(rag_quality, dict):
        out["rag_quality"] = rag_quality
    if isinstance(cov_rep, dict):
        out["coverage_ratio"] = cov_rep.get("coverage_ratio")
    return out


_OLLAMA_TRACE_MSG_PREVIEW = 300
_OLLAMA_TRACE_MSG_FULL_CAP = 32_768
_TOOL_LOOP_FINALIZE_WHITELIST = frozenset(
    {"shell", "bash", "web_search", "file_search", "grep", "read", "glob", "task"}
)


def _tool_loop_needs_finalize_nudge(tool_loop_stats: dict[str, Any] | None) -> bool:
    """Recommend a finalize nudge after many single-tool rounds (any tool name possible)."""
    if not isinstance(tool_loop_stats, dict):
        return False
    singles = int(tool_loop_stats.get("single_tool_rounds") or 0)
    rounds = int(tool_loop_stats.get("rounds") or 0)
    dominant = str(tool_loop_stats.get("dominant_tool") or "").strip().lower()
    dom_rounds = int(tool_loop_stats.get("dominant_tool_rounds") or 0)
    if rounds >= 25:
        return True
    if singles < 3:
        return False
    if dominant in _TOOL_LOOP_FINALIZE_WHITELIST and dom_rounds >= 3:
        return True
    if dominant and dom_rounds >= 8:
        return True
    return False


def _serialized_upstream_messages_chars(messages: list[Any]) -> int:
    try:
        return len(json.dumps(messages, ensure_ascii=False))
    except (TypeError, ValueError):
        run = 0
        for m in messages:
            if isinstance(m, dict):
                run += len(_ollama_message_content_str(m.get("content")))
                tc = m.get("tool_calls")
                if tc is not None:
                    try:
                        run += len(json.dumps(tc, ensure_ascii=False))
                    except (TypeError, ValueError):
                        run += len(str(tc))
            else:
                run += len(str(m))
        return run


def _truncate_old_tool_outputs_for_upstream_budget(
    messages: list[Any],
    *,
    budget_json_chars: int,
    per_message_ceiling: int = 12_000,
    preserve_tail_tool_roles: int = 24,
) -> tuple[list[Any], dict[str, Any]]:
    """Shorten oldest tool message bodies until JSON(serialized messages) fits the budget."""
    start_chars = _serialized_upstream_messages_chars(messages)
    diag: dict[str, Any] = {
        "original_upstream_json_chars": start_chars,
        "budget_json_chars": int(budget_json_chars),
    }
    if start_chars <= budget_json_chars:
        diag["compacted"] = False
        return messages, diag

    out: list[Any] = []
    for m in messages:
        out.append(dict(m) if isinstance(m, dict) else m)

    tool_indices = [
        i
        for i, m in enumerate(out)
        if isinstance(m, dict) and str(m.get("role") or "").strip().lower() == "tool"
    ]
    protected_tail = frozenset(tool_indices[-preserve_tail_tool_roles:])
    shortened_total = 0
    ceilings = (
        per_message_ceiling,
        max(4096, per_message_ceiling // 3),
        4096,
        2048,
        1024,
        512,
    )

    def _trim_once(ceiling: int) -> int:
        nonlocal shortened_total
        changed = 0
        for i in tool_indices:
            if i in protected_tail:
                continue
            m = out[i]
            if not isinstance(m, dict):
                continue
            raw_content = m.get("content")
            s = _ollama_message_content_str(raw_content)
            if len(s) <= ceiling:
                continue
            drop = len(s) - ceiling
            m["content"] = (
                f"{s[:ceiling].rstrip()}\n\n... [truncated {drop} chars for upstream budget]"
            )
            changed += 1
            shortened_total += 1
        return changed

    for ceil in ceilings:
        _trim_once(ceil)
        cur = _serialized_upstream_messages_chars(out)
        if cur <= budget_json_chars:
            diag["compacted"] = True
            diag["final_upstream_json_chars"] = cur
            diag["tool_messages_shortened_rounds"] = shortened_total
            diag["applied_ceiling"] = ceil
            return out, diag

    diag["compacted"] = True
    diag["still_over_budget_after_tool_trim"] = True
    diag["final_upstream_json_chars"] = _serialized_upstream_messages_chars(out)
    diag["tool_messages_shortened_rounds"] = shortened_total
    return out, diag


def _compact_upstream_messages_for_budget(
    messages: list[Any],
    *,
    budget_json_chars: int,
    preserve_tail_tool_roles: int = 12,
) -> tuple[list[Any], dict[str, Any]]:
    """Compact old chat/tool history until upstream JSON fits the input budget."""
    out, diag = _truncate_old_tool_outputs_for_upstream_budget(
        messages,
        budget_json_chars=budget_json_chars,
        per_message_ceiling=8_000,
        preserve_tail_tool_roles=preserve_tail_tool_roles,
    )
    if _serialized_upstream_messages_chars(out) <= budget_json_chars:
        return out, diag

    out = [dict(m) if isinstance(m, dict) else m for m in out]
    last_user_idx = -1
    for i in range(len(out) - 1, -1, -1):
        m = out[i]
        if isinstance(m, dict) and str(m.get("role") or "").strip().lower() == "user":
            last_user_idx = i
            break

    assistant_trimmed = 0
    tool_call_args_trimmed = 0
    message_summarized = 0
    for ceiling in (2048, 1024, 512, 256):
        for i, m in enumerate(out):
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "").strip().lower()
            if role == "system" or i == last_user_idx:
                continue
            if role == "assistant":
                content = _ollama_message_content_str(m.get("content"))
                if len(content) > ceiling:
                    m["content"] = (
                        f"{content[:ceiling].rstrip()}\n\n... [truncated {len(content) - ceiling} chars for upstream budget]"
                    )
                    assistant_trimmed += 1
                tool_calls = m.get("tool_calls")
                if isinstance(tool_calls, list):
                    next_calls: list[Any] = []
                    for tc in tool_calls:
                        if not isinstance(tc, dict):
                            next_calls.append(tc)
                            continue
                        tco = dict(tc)
                        fn = tco.get("function") if isinstance(tco.get("function"), dict) else None
                        if isinstance(fn, dict):
                            fno = dict(fn)
                            args = fno.get("arguments")
                            if isinstance(args, str) and len(args) > ceiling:
                                fno["arguments"] = (
                                    f"{args[:ceiling].rstrip()}\n\n... [truncated {len(args) - ceiling} chars for upstream budget]"
                                )
                                tool_call_args_trimmed += 1
                            tco["function"] = fno
                        next_calls.append(tco)
                    m["tool_calls"] = next_calls
            elif role == "tool" and i != last_user_idx:
                content = _ollama_message_content_str(m.get("content"))
                if len(content) > ceiling:
                    m["content"] = (
                        f"{content[:ceiling].rstrip()}\n\n... [truncated {len(content) - ceiling} chars for upstream budget]"
                    )
                    message_summarized += 1
        if _serialized_upstream_messages_chars(out) <= budget_json_chars:
            break

    final_chars = _serialized_upstream_messages_chars(out)
    diag["compacted"] = bool(diag.get("compacted")) or final_chars < int(diag.get("original_upstream_json_chars") or final_chars)
    diag["final_upstream_json_chars"] = final_chars
    if assistant_trimmed:
        diag["assistant_messages_shortened_rounds"] = assistant_trimmed
    if tool_call_args_trimmed:
        diag["assistant_tool_call_arguments_shortened_rounds"] = tool_call_args_trimmed
    if message_summarized:
        diag["tool_messages_extra_shortened_rounds"] = message_summarized
    if final_chars > budget_json_chars:
        diag["still_over_budget_after_history_compaction"] = True
    return out, diag


def _ollama_message_content_str(content: Any) -> str:
    """String form of an Ollama message ``content`` for logging / token estimates."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return json.dumps(content, ensure_ascii=False)
    if content is None:
        return ""
    return str(content)


def _trace_ollama_messages_for_ui(ollama_messages: list[Any]) -> list[dict[str, Any]]:
    """Snapshots messages for Proxy Trace (preview + capped full text for the WebUI modal)."""
    cap = max(4096, int(_OLLAMA_TRACE_MSG_FULL_CAP))
    out: list[dict[str, Any]] = []
    for m in ollama_messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role") or ""
        _raw_content = m.get("content")
        content_str = _ollama_message_content_str(_raw_content)
        content_len = len(content_str)
        lim = _OLLAMA_TRACE_MSG_PREVIEW
        truncated = content_len > cap
        displayed_full = content_str[:cap] + (f"... [truncated {content_len - cap} chars]" if truncated else "")
        entry: dict[str, Any] = {
            "role": str(role),
            "content_length_chars": int(content_len),
            "content_preview": content_str[:lim] + ("..." if content_len > lim else ""),
            "content_full": displayed_full,
        }
        if truncated:
            entry["content_full_was_truncated"] = True
        _imgs = m.get("images")
        if isinstance(_imgs, list) and _imgs:
            entry["images_count"] = len(_imgs)
        out.append(entry)
    return out


def _sanitize_tool_name(raw: object, *, fallback: str = "tool") -> str:
    if isinstance(raw, str):
        name = raw.strip()
        if name:
            return name
    return fallback


def _non_empty_str(raw: object) -> str:
    if isinstance(raw, str):
        s = raw.strip()
        if s:
            return s
        return ""
    if raw is None:
        return ""
    s = str(raw).strip()
    return s if s else ""


def _message_tool_call_id(message: dict[str, Any]) -> str:
    for key in ("tool_call_id", "tool_callid", "call_id", "id"):
        value = message.get(key)
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
    return ""


def _resolve_trace_chain_id(
    *,
    client_request_id: object,
    proxy_trace_meta: dict[str, Any] | None,
) -> tuple[str, str]:
    """
    Resolve stable UI chain key for consecutive requests.

    Priority:
    1) explicit ``client_request_id`` from payload
    2) inbound request id propagated via ``_proxy_trace_meta``
    """
    client_id = _non_empty_str(client_request_id)
    if client_id:
        return client_id, "client_request_id"

    meta = proxy_trace_meta if isinstance(proxy_trace_meta, dict) else {}
    for key in ("incoming_request_id", "x_trace_id", "x_request_id", "request_id", "trace_id"):
        value = _non_empty_str(meta.get(key))
        if value:
            return value, "incoming_request_id"
    return "", ""


_THOUGHT_SIGNATURE_SKIP_VALIDATOR = "skip_thought_signature_validator"
_GEMINI_TOOL_STATE_TTL_SECONDS = 7 * 24 * 60 * 60
_GEMINI_TOOL_STATE_SCHEMA_INIT_LOCK = threading.Lock()
_GEMINI_TOOL_STATE_SCHEMA_INIT_PATHS: set[str] = set()


def _is_gemini_model_name(model_name: str | None) -> bool:
    return is_gemini_family_model_name(model_name)


def _resolve_default_webui_db_path() -> str:
    env_path = os.getenv("WEBUI_DB_PATH")
    if env_path:
        return env_path
    project_root = Path(__file__).resolve().parents[3]
    return str(project_root / "logs" / "webui.db")


def _resolve_proxy_db_path_from_wiring(w: LlmProxyWiring | None) -> str:
    if w is not None:
        try:
            repo = w.get_logs_repository()
            path = getattr(repo, "db_path", None)
            if path:
                return str(path)
        except Exception:
            pass
    return _resolve_default_webui_db_path()


def _ensure_gemini_tool_state_schema(db_path: str) -> None:
    p = str(db_path or "").strip()
    if not p:
        return
    with _GEMINI_TOOL_STATE_SCHEMA_INIT_LOCK:
        if p in _GEMINI_TOOL_STATE_SCHEMA_INIT_PATHS:
            return
    try:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(p) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gemini_tool_call_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    function_name TEXT,
                    thought_signature TEXT,
                    trace_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(call_id, model)
                );
                CREATE INDEX IF NOT EXISTS idx_gemini_tool_call_state_call_id
                    ON gemini_tool_call_state(call_id);
                CREATE INDEX IF NOT EXISTS idx_gemini_tool_call_state_updated_at
                    ON gemini_tool_call_state(updated_at);
                """
            )
            conn.commit()
    except Exception:
        return
    with _GEMINI_TOOL_STATE_SCHEMA_INIT_LOCK:
        _GEMINI_TOOL_STATE_SCHEMA_INIT_PATHS.add(p)


def _gemini_tool_state_lookup(
    db_path: str | None,
    *,
    call_id: str,
    model_name: str | None,
) -> dict[str, str]:
    cid = str(call_id or "").strip()
    path = str(db_path or "").strip()
    if not cid or not path:
        return {}
    _ensure_gemini_tool_state_schema(path)
    model = str(model_name or "").strip()
    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            row = None
            if model:
                row = conn.execute(
                    """
                    SELECT function_name, thought_signature
                    FROM gemini_tool_call_state
                    WHERE call_id = ? AND model = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (cid, model),
                ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT function_name, thought_signature
                    FROM gemini_tool_call_state
                    WHERE call_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (cid,),
                ).fetchone()
            if row is None:
                return {}
            out: dict[str, str] = {}
            fn = row["function_name"]
            sig = row["thought_signature"]
            if isinstance(fn, str) and fn.strip():
                out["function_name"] = fn.strip()
            if isinstance(sig, str) and sig.strip():
                out["thought_signature"] = sig.strip()
            return out
    except Exception:
        return {}


def _gemini_tool_state_upsert_many(
    db_path: str | None,
    *,
    rows: list[dict[str, str]],
    ttl_seconds: int = _GEMINI_TOOL_STATE_TTL_SECONDS,
) -> int:
    path = str(db_path or "").strip()
    if not path or not rows:
        return 0
    _ensure_gemini_tool_state_schema(path)
    payload: list[tuple[str, str, str, str, str]] = []
    for row in rows:
        call_id = str(row.get("call_id") or "").strip()
        model = str(row.get("model") or "").strip()
        if not call_id or not model:
            continue
        payload.append(
            (
                call_id,
                model,
                str(row.get("function_name") or "").strip(),
                str(row.get("thought_signature") or "").strip(),
                str(row.get("trace_id") or "").strip(),
            )
        )
    if not payload:
        return 0
    try:
        with sqlite3.connect(path) as conn:
            conn.executemany(
                """
                INSERT INTO gemini_tool_call_state
                    (call_id, model, function_name, thought_signature, trace_id, created_at, updated_at)
                VALUES (?, ?, NULLIF(?, ''), NULLIF(?, ''), NULLIF(?, ''), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(call_id, model) DO UPDATE SET
                    function_name = COALESCE(excluded.function_name, gemini_tool_call_state.function_name),
                    thought_signature = COALESCE(excluded.thought_signature, gemini_tool_call_state.thought_signature),
                    trace_id = COALESCE(excluded.trace_id, gemini_tool_call_state.trace_id),
                    updated_at = CURRENT_TIMESTAMP
                """,
                payload,
            )
            ttl = max(int(ttl_seconds or 0), 60)
            conn.execute(
                "DELETE FROM gemini_tool_call_state WHERE updated_at < datetime('now', ?)",
                (f"-{ttl} seconds",),
            )
            conn.commit()
    except Exception:
        return 0
    return len(payload)


def _build_tool_call_id_to_name(messages: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in messages:
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        tool_calls = m.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for c in tool_calls:
            if not isinstance(c, dict):
                continue
            call_id = _message_tool_call_id(c)
            fn = c.get("function") if isinstance(c.get("function"), dict) else {}
            name = _sanitize_tool_name(fn.get("name") if isinstance(fn, dict) else None, fallback="")
            if call_id and name:
                out[call_id] = name
    return out


def _build_tool_call_id_to_signature(messages: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in messages:
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        tool_calls = m.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for c in tool_calls:
            if not isinstance(c, dict):
                continue
            call_id = _message_tool_call_id(c)
            if not call_id:
                continue
            fn = c.get("function") if isinstance(c.get("function"), dict) else {}
            sig = _extract_tool_call_thought_signature(c, fn if isinstance(fn, dict) else {})
            if sig:
                out[call_id] = sig
    return out


def _preflight_native_tool_messages(
    messages: list[Any],
    *,
    model_name: str | None = None,
    trace_id: str | None = None,
    db_path: str | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    tool_call_id_to_name = _build_tool_call_id_to_name(messages)
    tool_call_id_to_signature = _build_tool_call_id_to_signature(messages)
    corrected_indices: list[int] = []
    heuristic_indices: list[int] = []
    heuristic_source_counts: dict[str, int] = {"name_alias": 0, "call_id_map": 0, "fallback": 0}
    is_gemini = _is_gemini_model_name(model_name)
    effective_db_path = str(db_path or "").strip() or _resolve_default_webui_db_path()
    gemini_model = str(model_name or "").strip() or "gemini"
    gemini_signature_recovered_from_db = 0
    gemini_signature_recovered_from_history = 0
    gemini_signature_fallback_sentinel = 0
    gemini_tool_name_recovered_from_db = 0
    gemini_lookup_attempts = 0
    gemini_lookup_hits = 0
    gemini_lookup_cache: dict[str, dict[str, str]] = {}
    assistant_tool_call_fixed_indices: list[int] = []
    rows_to_upsert: list[dict[str, str]] = []
    out: list[Any] = []
    for idx, m in enumerate(messages):
        if not isinstance(m, dict):
            out.append(m)
            continue
        role = m.get("role")
        if role == "assistant":
            tool_calls = m.get("tool_calls")
            if not isinstance(tool_calls, list) or not tool_calls:
                out.append(m)
                continue
            changed = False
            new_calls: list[Any] = []
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    new_calls.append(tc)
                    continue
                tc2 = dict(tc)
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                fn2 = dict(fn) if isinstance(fn, dict) else {}
                call_id = _message_tool_call_id(tc2)
                if call_id:
                    if str(tc2.get("id") or "").strip() != call_id:
                        tc2["id"] = call_id
                        changed = True
                    if str(tc2.get("call_id") or "").strip() != call_id:
                        tc2["call_id"] = call_id
                        changed = True

                fn_name = _sanitize_tool_name(fn2.get("name"), fallback="")
                if not fn_name and call_id:
                    mapped_name = _sanitize_tool_name(tool_call_id_to_name.get(call_id), fallback="")
                    if mapped_name:
                        fn_name = mapped_name
                if not fn_name and is_gemini and call_id:
                    if call_id in gemini_lookup_cache:
                        rec = gemini_lookup_cache[call_id]
                    else:
                        gemini_lookup_attempts += 1
                        rec = _gemini_tool_state_lookup(
                            effective_db_path,
                            call_id=call_id,
                            model_name=gemini_model,
                        )
                        gemini_lookup_cache[call_id] = rec
                        if rec:
                            gemini_lookup_hits += 1
                    rec_name = _sanitize_tool_name(rec.get("function_name"), fallback="")
                    if rec_name:
                        fn_name = rec_name
                        gemini_tool_name_recovered_from_db += 1
                if fn_name and fn2.get("name") != fn_name:
                    fn2["name"] = fn_name
                    changed = True
                if call_id and fn_name:
                    tool_call_id_to_name.setdefault(call_id, fn_name)

                thought_signature = _extract_tool_call_thought_signature(tc2, fn2)
                if not thought_signature and call_id:
                    mapped_sig = str(tool_call_id_to_signature.get(call_id) or "").strip()
                    if mapped_sig:
                        thought_signature = mapped_sig
                        gemini_signature_recovered_from_history += 1
                if not thought_signature and is_gemini and call_id:
                    if call_id in gemini_lookup_cache:
                        rec = gemini_lookup_cache[call_id]
                    else:
                        gemini_lookup_attempts += 1
                        rec = _gemini_tool_state_lookup(
                            effective_db_path,
                            call_id=call_id,
                            model_name=gemini_model,
                        )
                        gemini_lookup_cache[call_id] = rec
                        if rec:
                            gemini_lookup_hits += 1
                    rec_sig = str(rec.get("thought_signature") or "").strip()
                    if rec_sig:
                        thought_signature = rec_sig
                        gemini_signature_recovered_from_db += 1
                if not thought_signature and is_gemini:
                    thought_signature = _THOUGHT_SIGNATURE_SKIP_VALIDATOR
                    gemini_signature_fallback_sentinel += 1
                if thought_signature:
                    if fn2.get("thought_signature") != thought_signature:
                        fn2["thought_signature"] = thought_signature
                        changed = True
                    extra = tc2.get("extra_content")
                    extra_out = dict(extra) if isinstance(extra, dict) else {}
                    google = extra_out.get("google")
                    google_out = dict(google) if isinstance(google, dict) else {}
                    if google_out.get("thought_signature") != thought_signature:
                        google_out["thought_signature"] = thought_signature
                        changed = True
                    extra_out["google"] = google_out
                    tc2["extra_content"] = extra_out
                    if call_id:
                        tool_call_id_to_signature.setdefault(call_id, thought_signature)

                if fn2 != fn:
                    tc2["function"] = fn2
                    changed = True

                if is_gemini and call_id:
                    rows_to_upsert.append(
                        {
                            "call_id": call_id,
                            "model": gemini_model,
                            "function_name": fn_name,
                            "thought_signature": thought_signature,
                            "trace_id": str(trace_id or ""),
                        }
                    )
                new_calls.append(tc2)

            if changed:
                m2 = dict(m)
                m2["tool_calls"] = new_calls
                out.append(m2)
                assistant_tool_call_fixed_indices.append(idx)
            else:
                out.append(m)
            continue

        if role != "tool":
            out.append(m)
            continue
        name = _sanitize_tool_name(m.get("tool_name"), fallback="")
        heuristic_source = ""
        if not name:
            alias_name = _sanitize_tool_name(m.get("name"), fallback="")
            if alias_name:
                name = alias_name
                heuristic_source = "name_alias"
        if not name:
            call_id = _message_tool_call_id(m)
            if call_id:
                mapped_name = _sanitize_tool_name(tool_call_id_to_name.get(call_id), fallback="")
                if mapped_name:
                    name = mapped_name
                    heuristic_source = "call_id_map"
                elif is_gemini:
                    if call_id in gemini_lookup_cache:
                        rec = gemini_lookup_cache[call_id]
                    else:
                        gemini_lookup_attempts += 1
                        rec = _gemini_tool_state_lookup(
                            effective_db_path,
                            call_id=call_id,
                            model_name=gemini_model,
                        )
                        gemini_lookup_cache[call_id] = rec
                        if rec:
                            gemini_lookup_hits += 1
                    rec_name = _sanitize_tool_name(rec.get("function_name"), fallback="")
                    if rec_name:
                        name = rec_name
                        heuristic_source = "call_id_map"
                        gemini_tool_name_recovered_from_db += 1
        if not name:
            name = "tool"
            heuristic_source = "fallback"

        if heuristic_source:
            heuristic_indices.append(idx)
            heuristic_source_counts[heuristic_source] = int(heuristic_source_counts.get(heuristic_source) or 0) + 1

        if m.get("tool_name") != name or m.get("name") != name:
            m2 = dict(m)
            m2["tool_name"] = name
            m2["name"] = name
            out.append(m2)
            corrected_indices.append(idx)
        else:
            out.append(m)
    diag: dict[str, Any] = {}
    if assistant_tool_call_fixed_indices:
        diag["assistant_tool_call_fixes"] = len(assistant_tool_call_fixed_indices)
        diag["assistant_tool_call_fixed_indices"] = assistant_tool_call_fixed_indices[:10]
    if corrected_indices:
        diag["tool_message_name_fixes"] = len(corrected_indices)
        diag["tool_message_name_fixed_indices"] = corrected_indices[:10]
    if heuristic_indices:
        diag["tool_message_name_recovered_heuristic_count"] = len(heuristic_indices)
        diag["tool_message_name_recovered_heuristic_indices"] = heuristic_indices[:10]
        diag["tool_message_name_recovered_heuristic_sources"] = {
            k: v for k, v in heuristic_source_counts.items() if int(v) > 0
        }
    if is_gemini:
        if gemini_lookup_attempts:
            diag["gemini_tool_state_lookup_attempts"] = int(gemini_lookup_attempts)
            diag["gemini_tool_state_lookup_hits"] = int(gemini_lookup_hits)
        if gemini_signature_recovered_from_history:
            diag["gemini_signature_recovered_from_history_count"] = int(
                gemini_signature_recovered_from_history
            )
        if gemini_signature_recovered_from_db:
            diag["gemini_signature_recovered_from_db_count"] = int(gemini_signature_recovered_from_db)
        if gemini_signature_fallback_sentinel:
            diag["gemini_signature_fallback_sentinel_count"] = int(gemini_signature_fallback_sentinel)
        if gemini_tool_name_recovered_from_db:
            diag["gemini_tool_name_recovered_from_db_count"] = int(gemini_tool_name_recovered_from_db)
        if rows_to_upsert:
            upserted = _gemini_tool_state_upsert_many(
                effective_db_path,
                rows=rows_to_upsert,
            )
            if upserted:
                diag["gemini_tool_state_upserted_count"] = int(upserted)
    return out, diag


_GEMINI_SAFE_SCHEMA_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


def _normalize_schema_for_gemini(raw_schema: Any) -> tuple[dict[str, Any], int]:
    relaxed = 0

    def _norm(node: Any) -> dict[str, Any]:
        nonlocal relaxed
        if not isinstance(node, dict):
            relaxed += 1
            return {"type": "object", "additionalProperties": True}

        out: dict[str, Any] = {}
        node_type = node.get("type")
        if isinstance(node_type, str):
            t = node_type.strip().lower()
            if t in _GEMINI_SAFE_SCHEMA_TYPES:
                out["type"] = t
            elif t:
                relaxed += 1
        elif node_type is not None:
            relaxed += 1

        desc = node.get("description")
        if isinstance(desc, str) and desc.strip():
            out["description"] = desc.strip()
        elif desc is not None:
            relaxed += 1

        enum_raw = node.get("enum")
        if isinstance(enum_raw, list):
            enum_values = [v for v in enum_raw if not isinstance(v, (dict, list))]
            if enum_values:
                out["enum"] = enum_values
            elif enum_raw:
                relaxed += 1
        elif enum_raw is not None:
            relaxed += 1

        object_like = (
            out.get("type") == "object"
            or "properties" in node
            or "required" in node
            or "additionalProperties" in node
        )
        if object_like:
            out.setdefault("type", "object")
            props_in = node.get("properties")
            props_out: dict[str, Any] = {}
            if isinstance(props_in, dict):
                for key, val in props_in.items():
                    if not isinstance(key, str):
                        relaxed += 1
                        continue
                    k = key.strip()
                    if not k:
                        relaxed += 1
                        continue
                    props_out[k] = _norm(val)
            elif props_in is not None:
                relaxed += 1
            out["properties"] = props_out

            required_in = node.get("required")
            if isinstance(required_in, list):
                required_out: list[str] = []
                for raw in required_in:
                    if not isinstance(raw, str):
                        relaxed += 1
                        continue
                    r = raw.strip()
                    if not r:
                        relaxed += 1
                        continue
                    if props_out and r not in props_out:
                        relaxed += 1
                        continue
                    if r not in required_out:
                        required_out.append(r)
                if required_out:
                    out["required"] = required_out
            elif required_in is not None:
                relaxed += 1

            addl = node.get("additionalProperties")
            if isinstance(addl, bool):
                out["additionalProperties"] = addl
            elif isinstance(addl, dict):
                out["additionalProperties"] = _norm(addl)
            elif addl is not None:
                relaxed += 1
            elif not props_out:
                out["additionalProperties"] = True

        array_like = out.get("type") == "array" or "items" in node
        if array_like:
            out.setdefault("type", "array")
            items_in = node.get("items")
            if isinstance(items_in, dict):
                out["items"] = _norm(items_in)
            elif isinstance(items_in, list) and items_in:
                head = items_in[0]
                out["items"] = _norm(head if isinstance(head, dict) else {"type": "object"})
                if len(items_in) > 1:
                    relaxed += len(items_in) - 1
            else:
                out["items"] = {"type": "object", "additionalProperties": True}
                if items_in is not None:
                    relaxed += 1

        if "type" not in out:
            out["type"] = "object"
            out.setdefault("additionalProperties", True)
        return out

    seed = raw_schema if isinstance(raw_schema, dict) else {"type": "object", "additionalProperties": True}
    if raw_schema is not None and not isinstance(raw_schema, dict):
        relaxed += 1
    return _norm(seed), relaxed


def _interpolate_native_tools_for_gemini(
    tools: list[Any],
    *,
    model_name: str | None,
) -> tuple[list[Any], dict[str, Any]]:
    if not _is_gemini_model_name(model_name):
        return tools, {}

    changed = 0
    relaxed_total = 0
    normalized: list[tuple[int, Any]] = []

    for idx, tool in enumerate(tools):
        if not isinstance(tool, dict):
            normalized.append((idx, tool))
            continue
        ttype = str(tool.get("type") or "").strip().lower()
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        if ttype not in ("", "function") or not isinstance(fn, dict):
            normalized.append((idx, tool))
            continue

        fn_name = _sanitize_tool_name(fn.get("name"), fallback="")
        if not fn_name:
            fn_name = _sanitize_tool_name(tool.get("name"), fallback="")
        if not fn_name:
            normalized.append((idx, tool))
            continue

        fn_out = dict(fn)
        fn_out["name"] = fn_name
        description = str(fn_out.get("description") or tool.get("description") or "").strip()
        if not description:
            description = f"IDE tool `{fn_name}`."
        fn_out["description"] = description

        raw_params = fn_out.get("parameters")
        if not isinstance(raw_params, dict):
            raw_params = tool.get("parameters")
        params_out, relaxed = _normalize_schema_for_gemini(raw_params)
        fn_out["parameters"] = params_out
        relaxed_total += int(relaxed)

        if not isinstance(fn_out.get("strict"), bool):
            fn_out.pop("strict", None)

        tool_out = dict(tool)
        tool_out["type"] = "function"
        tool_out["function"] = fn_out

        if tool_out != tool:
            changed += 1
        normalized.append((idx, tool_out))

    ordered = sorted(
        normalized,
        key=lambda pair: (
            0
            if isinstance(pair[1], dict)
            and isinstance((pair[1].get("function") if isinstance(pair[1].get("function"), dict) else {}), dict)
            and _sanitize_tool_name(
                ((pair[1].get("function") if isinstance(pair[1].get("function"), dict) else {})).get("name"),
                fallback="",
            )
            else 1,
            _sanitize_tool_name(
                (
                    ((pair[1].get("function") if isinstance(pair[1], dict) and isinstance(pair[1].get("function"), dict) else {}))
                    .get("name")
                ),
                fallback="\uffff",
            ).lower(),
            pair[0],
        ),
    )
    out = [item for _, item in ordered]

    diag: dict[str, Any] = {"gemini_tool_interpolation_enabled": True}
    if changed:
        diag["gemini_tool_schema_normalized_count"] = int(changed)
    if relaxed_total:
        diag["gemini_tool_schema_relaxed_count"] = int(relaxed_total)
    if [idx for idx, _ in normalized] != [idx for idx, _ in ordered]:
        diag["gemini_tool_order_stabilized"] = True
    return out, diag


def _preflight_native_tools_payload(tools: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for idx, t in enumerate(tools):
        if not isinstance(t, dict):
            dropped.append({"index": idx, "reason": "non_dict"})
            continue
        ttype = str(t.get("type") or "").strip().lower()
        fn = t.get("function") if isinstance(t.get("function"), dict) else {}
        if not isinstance(fn, dict):
            fn = {}
        fn_name = _sanitize_tool_name(fn.get("name"), fallback="")
        if not fn_name:
            fn_name = _sanitize_tool_name(t.get("name"), fallback="")
        if ttype not in ("", "function") or not fn_name:
            dropped.append({"index": idx, "type": ttype or "unknown", "reason": "unsupported_or_missing_name"})
            continue
        fn_out = dict(fn)
        fn_out["name"] = fn_name
        t_out = dict(t)
        t_out["type"] = "function"
        t_out["function"] = fn_out
        valid.append(t_out)
    diag: dict[str, Any] = {}
    if dropped:
        diag["tools_dropped_count"] = len(dropped)
        diag["tools_dropped"] = dropped[:10]
    return valid, diag


def _tool_round_stats_since_last_user(messages: list[Any]) -> dict[str, Any]:
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "user":
            last_user_idx = i
            break
    rounds = 0
    shell_rounds = 0
    non_shell_rounds = 0
    single_tool_rounds = 0
    tool_name_counts: dict[str, int] = {}
    for m in messages[last_user_idx + 1 :]:
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        tool_calls = m.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            continue
        rounds += 1
        names: list[str] = []
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            if isinstance(fn, dict):
                names.append(str(fn.get("name") or "").strip().lower())
        if len(names) == 1 and names[0]:
            single_tool_rounds += 1
            tool_name_counts[names[0]] = int(tool_name_counts.get(names[0]) or 0) + 1
        if names and all(n == "shell" for n in names):
            shell_rounds += 1
        else:
            non_shell_rounds += 1
    dominant_tool = ""
    dominant_count = 0
    for name, count in tool_name_counts.items():
        if count > dominant_count:
            dominant_tool = name
            dominant_count = count
    return {
        "rounds": rounds,
        "shell_rounds": shell_rounds,
        "non_shell_rounds": non_shell_rounds,
        "single_tool_rounds": single_tool_rounds,
        "dominant_tool": dominant_tool,
        "dominant_tool_rounds": dominant_count,
    }


_POWERSHELL_COMMAND_WRAPPER_RE = re.compile(
    r"""^\s*(?P<exe>(?:powershell|pwsh)(?:\.exe)?)\s+-Command\s+(?P<q>["'])(?P<script>.*)(?P=q)\s*$""",
    re.IGNORECASE | re.DOTALL,
)




def _looks_like_recursive_get_child_item(cmd: str) -> bool:
    c = cmd.lower()
    return ("get-childitem" in c or "\ngci " in f"\n{c}" or "\ndir " in f"\n{c}" or "\nls " in f"\n{c}") and (
        "-recurse" in c
    )


def _ensure_safe_windows_listing_command(cmd: str) -> str:
    """Avoid hard failures on ACL-protected folders for recursive PowerShell listing."""
    if not isinstance(cmd, str):
        return cmd
    if not _looks_like_recursive_get_child_item(cmd):
        return cmd
    if re.search(r"(?i)-ErrorAction\b", cmd):
        return cmd

    m = _POWERSHELL_COMMAND_WRAPPER_RE.match(cmd)
    if m:
        script = m.group("script")
        if not re.search(r"(?i)-ErrorAction\b", script):
            script = script.rstrip() + " -ErrorAction SilentlyContinue"
        return f'{m.group("exe")} -Command {m.group("q")}{script}{m.group("q")}'

    return cmd.rstrip() + " -ErrorAction SilentlyContinue"


def _sanitize_outgoing_shell_tool_calls(tool_calls: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    if not tool_calls:
        return tool_calls, 0
    out: list[dict[str, Any]] = []
    fixed = 0
    for tc in tool_calls:
        if not isinstance(tc, dict):
            out.append(tc)
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = str(fn.get("name") or "").strip().lower() if isinstance(fn, dict) else ""
        if name != "shell":
            out.append(tc)
            continue
        args_raw = fn.get("arguments") if isinstance(fn, dict) else None
        args_obj: dict[str, Any] | None = None
        if isinstance(args_raw, str):
            try:
                parsed = json.loads(args_raw)
                if isinstance(parsed, dict):
                    args_obj = parsed
            except json.JSONDecodeError:
                args_obj = None
        elif isinstance(args_raw, dict):
            args_obj = dict(args_raw)
        if not isinstance(args_obj, dict):
            out.append(tc)
            continue
        cmd = args_obj.get("command")
        if not isinstance(cmd, str):
            out.append(tc)
            continue
        safe_cmd = _ensure_safe_windows_listing_command(cmd)
        if safe_cmd == cmd:
            out.append(tc)
            continue
        args_obj["command"] = safe_cmd
        fn2 = dict(fn)
        fn2["arguments"] = json.dumps(args_obj, ensure_ascii=False)
        tc2 = dict(tc)
        tc2["function"] = fn2
        out.append(tc2)
        fixed += 1
    return out, fixed


def _extract_tool_call_thought_signature(tc: dict[str, Any], fn: dict[str, Any]) -> str:
    candidates: list[Any] = []
    if isinstance(fn, dict):
        candidates.extend((fn.get("thought_signature"), fn.get("thoughtSignature")))
    candidates.extend((tc.get("thought_signature"), tc.get("thoughtSignature")))
    extra = tc.get("extra_content")
    if isinstance(extra, dict):
        google = extra.get("google")
        if isinstance(google, dict):
            candidates.extend((google.get("thought_signature"), google.get("thoughtSignature")))
    for raw in candidates:
        if isinstance(raw, str):
            s = raw.strip()
            if s:
                return s
    return ""


def _extract_tool_call_function_name(tc: dict[str, Any]) -> str:
    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
    return _sanitize_tool_name(fn.get("name") if isinstance(fn, dict) else None, fallback="")


def _persist_gemini_tool_calls_state(
    *,
    tool_calls: list[Any] | None,
    model_name: str | None,
    trace_id: str | None,
    db_path: str | None,
) -> int:
    if not _is_gemini_model_name(model_name):
        return 0
    if not isinstance(tool_calls, list) or not tool_calls:
        return 0
    model = str(model_name or "").strip() or "gemini"
    rows: list[dict[str, str]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        call_id = _message_tool_call_id(tc)
        if not call_id:
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = _extract_tool_call_function_name(tc)
        sig = _extract_tool_call_thought_signature(tc, fn if isinstance(fn, dict) else {})
        rows.append(
            {
                "call_id": call_id,
                "model": model,
                "function_name": name,
                "thought_signature": sig,
                "trace_id": str(trace_id or ""),
            }
        )
    if not rows:
        return 0
    return _gemini_tool_state_upsert_many(db_path or _resolve_default_webui_db_path(), rows=rows)


def _sse_tool_calls_payload(tool_calls: list[Any]) -> list[dict[str, object]]:
    payload_calls: list[dict[str, object]] = []
    for i, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        fn_payload: dict[str, object] = {
            "name": fn.get("name"),
            "arguments": fn.get("arguments"),
        }
        call_id = tc.get("id") if tc.get("id") is not None else tc.get("call_id")
        call_payload: dict[str, object] = {
            "index": i,
            "id": call_id,
            "call_id": call_id,
            "type": "function",
            "function": fn_payload,
        }
        thought_signature = _extract_tool_call_thought_signature(tc, fn)
        extra = tc.get("extra_content")
        extra_out = dict(extra) if isinstance(extra, dict) else {}
        if thought_signature:
            fn_payload["thought_signature"] = thought_signature
            google = extra_out.get("google")
            if isinstance(google, dict):
                google_out = dict(google)
            else:
                google_out = {}
            google_out.setdefault("thought_signature", thought_signature)
            extra_out["google"] = google_out
        if extra_out:
            call_payload["extra_content"] = extra_out
        payload_calls.append(call_payload)
    return payload_calls


def _merge_ollama_visible_text(thinking: str | None, content: str | None) -> str:
    """Single assistant string for the client: thinking then content when both exist."""
    t = (thinking or "").strip()
    c = (content or "").strip()
    if t and c:
        return f"{t}\n\n{c}"
    return c or t


def _assistant_text_parts(
    thinking: str | None,
    content: str | None,
) -> dict[str, str]:
    reasoning_content = (thinking or "").strip()
    final_content = (content or "").strip()
    return {
        "visible_content": _merge_ollama_visible_text(reasoning_content, final_content),
        "reasoning_content": reasoning_content,
        "final_content": final_content,
    }


def _assistant_text_parts_from_ollama_message(ollama_msg: dict[str, Any]) -> dict[str, str]:
    content = ollama_msg.get("content") if isinstance(ollama_msg.get("content"), str) else ""
    thinking = ollama_msg.get("thinking") if isinstance(ollama_msg.get("thinking"), str) else ""
    return _assistant_text_parts(thinking, content)


def _text_preview(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _apply_trace_response_text_fields(
    response: dict[str, Any],
    *,
    visible_content: str,
    reasoning_content: str,
    final_content: str,
    log_preview: int,
) -> None:
    response["content_preview"] = _text_preview(visible_content, log_preview)
    response["content_length_chars"] = len(visible_content)
    response["has_reasoning"] = bool(reasoning_content.strip())
    response["reasoning_preview"] = _text_preview(reasoning_content, log_preview)
    response["final_content_preview"] = _text_preview(final_content, log_preview)
    response["reasoning_chars"] = len(reasoning_content)
    response["final_content_chars"] = len(final_content)


def _positive_int_or_none(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _effective_num_predict(
    chat_client: Any,
    build_extra_options: dict[str, Any],
    chat_max_tokens: int | None,
) -> int | None:
    if chat_max_tokens is not None:
        return chat_max_tokens
    n = _positive_int_or_none(build_extra_options.get("num_predict"))
    if n is not None:
        return n
    default_options = getattr(chat_client, "_default_options", None)
    if isinstance(default_options, dict):
        return _positive_int_or_none(default_options.get("num_predict"))
    return None


def _effective_num_ctx(
    chat_client: Any,
    build_extra_options: dict[str, Any],
) -> int | None:
    n = _positive_int_or_none(build_extra_options.get("num_ctx"))
    if n is not None:
        return n
    default_options = getattr(chat_client, "_default_options", None)
    if isinstance(default_options, dict):
        return _positive_int_or_none(default_options.get("num_ctx"))
    return None


def _effective_max_agent_steps(active_build: dict[str, Any] | None) -> int | None:
    if not isinstance(active_build, dict):
        return None
    n = _positive_int_or_none(active_build.get("max_agent_steps"))
    if n is None:
        return None
    return max(1, min(n, 256))


def _input_budget_from_context(
    *,
    num_ctx: int | None,
    num_predict: int | None,
) -> dict[str, int] | None:
    if num_ctx is None or num_ctx <= 0 or num_predict is None or num_predict <= 0:
        return None
    safety_margin = max(4096, min(int(num_ctx / 32), 8192))
    input_budget = max(1024, int(num_ctx) - int(num_predict) - safety_margin)
    return {
        "num_ctx": int(num_ctx),
        "reserved_output_tokens": int(num_predict),
        "safety_margin_tokens": int(safety_margin),
        "input_budget_tokens": int(input_budget),
        "input_budget_json_chars": int(input_budget * 4),
    }


def _append_trace_warning(trace: dict[str, Any], code: str) -> None:
    warnings = trace.setdefault("warnings", [])
    if isinstance(warnings, list) and code not in warnings:
        warnings.append(code)


def _apply_response_diagnostics(trace: dict[str, Any]) -> None:
    req = trace.get("request") if isinstance(trace.get("request"), dict) else {}
    resp = trace.get("response") if isinstance(trace.get("response"), dict) else {}
    tool_calls_count = _positive_int_or_none(resp.get("tool_calls_count")) or 0
    reasoning_chars = _positive_int_or_none(resp.get("reasoning_chars")) or 0
    final_content_chars = _positive_int_or_none(resp.get("final_content_chars")) or 0
    if reasoning_chars > 0 and final_content_chars == 0 and tool_calls_count == 0:
        _append_trace_warning(trace, "reasoning_only_response")

    effective = _positive_int_or_none(req.get("effective_num_predict"))
    eval_count = _positive_int_or_none(resp.get("ollama_eval_count"))
    if eval_count is None:
        eval_count = _positive_int_or_none(resp.get("eval_count"))
    if effective is not None and eval_count is not None and eval_count >= effective:
        _append_trace_warning(trace, "output_token_budget_exhausted")


def _output_budget_exhaustion_error(trace: dict[str, Any], metrics_src: dict[str, Any] | None = None) -> str:
    req = trace.get("request") if isinstance(trace.get("request"), dict) else {}
    effective = _positive_int_or_none(req.get("effective_num_predict"))
    if effective is None:
        return ""
    eval_count = None
    if isinstance(metrics_src, dict):
        eval_count = _positive_int_or_none(metrics_src.get("eval_count"))
        if eval_count is None:
            eval_count = _positive_int_or_none(metrics_src.get("ollama_eval_count"))
    if eval_count is None:
        resp = trace.get("response") if isinstance(trace.get("response"), dict) else {}
        eval_count = _positive_int_or_none(resp.get("ollama_eval_count"))
        if eval_count is None:
            eval_count = _positive_int_or_none(resp.get("eval_count"))
    if eval_count is None or eval_count < effective:
        return ""
    return (
        f"[Error: output token budget exhausted: generated {eval_count} tokens reached "
        f"num_predict={effective}. Increase Model Build num_predict/max_tokens or shorten the prompt.]"
    )


def passthrough_think_from_body(body: dict[str, Any]) -> bool | str | None:
    """Pass Ollama ``think`` only when the client included the key (mediator; no derived mapping)."""
    if "think" not in body:
        return None
    raw = body.get("think")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (int, float)):
        if raw == 1:
            return True
        if raw == 0:
            return False
    return None


def _ollama_native_think_broken_for_model(model_name: str | None) -> bool:
    """Ollama native ``think`` with Qwen3 often returns only placeholder output (e.g. ``.``).

    Only matches the ``qwen3`` family (qwen3, qwen3:7b, etc.), NOT newer
    versions like ``qwen3.5``, ``qwen3.1`` where thinking works correctly.
    """
    name = (model_name or "").lower()
    idx = name.find("qwen3")
    if idx < 0:
        return False
    after = idx + 5  # position right after "qwen3"
    if after < len(name) and name[after] in ".0123456789":
        return False
    return True


def effective_ollama_think_from_body(
    body: dict[str, Any],
    ollama_model: str | None,
    *,
    capabilities: frozenset[str] | None = None,
) -> bool | str | None:
    """
    Value actually sent to Ollama ``/api/chat``.

    For the original Qwen3 family, omitting ``think`` often leaves the model's template with
    thinking enabled by default, which yields placeholder-only output.  Always send explicit
    ``think: false`` for those models.  Newer versions (qwen3.5, qwen3.1, …) are not affected.
    For other models, passthrough only when the client sent ``think`` (mediator).
    When ``capabilities`` is known and excludes thinking, omit ``think`` so Ollama uses model defaults.
    """
    raw = passthrough_think_from_body(body)
    if _ollama_native_think_broken_for_model(ollama_model):
        return False
    if capabilities is not None and raw is not None and not caps_supports_thinking(capabilities):
        return None
    return raw


_PLACEHOLDER_REPLY_FALLBACK_EN = (
    "The model returned only a placeholder fragment. Try again, shorten the prompt, or switch model. "
    "The system prompt already prioritizes your message and attachments over retrieved snippets."
)


def _is_placeholder_only_reply(text: str | None) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    if len(s) > 120:
        return False
    allowed = frozenset(".…\t\n\r ")
    return all(c in allowed for c in s)


def _is_micro_garbage_reply(text: str | None) -> bool:
    """Single-token fragments (e.g. one Russian inflected word) are not a real answer."""
    s = (text or "").strip()
    if len(s) < 4 or len(s) > 24:
        return False
    if any(c.isspace() for c in s):
        return False
    return all(c.isalnum() or c in "_-" for c in s)


def _degenerate_assistant_reply(text: str | None) -> bool:
    return _is_placeholder_only_reply(text) or _is_micro_garbage_reply(text)


def _trace_ollama_api_metrics(src: dict[str, Any] | None, model_id: str | None = None) -> dict[str, Any]:
    """Top-level Ollama /api/chat fields useful for diagnosing stop vs length truncation."""
    if not isinstance(src, dict):
        return {}
    out: dict[str, Any] = {}
    if src.get("done_reason") is not None:
        out["ollama_done_reason"] = src["done_reason"]
    for k in ("eval_count", "prompt_eval_count"):
        if src.get(k) is not None:
            out[f"ollama_{k}"] = src[k]
            out[k] = src[k]
    if model_id:
        brand_key = resolve_brand_key(model_id, show_payload=src)
        if brand_key:
            out["brand_key"] = brand_key
    return out


def _proxy_ollama_chat_text_parts(
    chat_client: Any,
    messages: list[dict[str, Any]],
    model: str,
    think: bool | str | None,
    *,
    options_overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Non-stream /api/chat; returns separated text parts plus merged visible content."""
    _co = dict(getattr(chat_client, "_default_options", None) or {})
    if options_overlay:
        _co.update(options_overlay)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": dict(_co),
    }
    if think is not None:
        payload["think"] = think
    chat_fn = getattr(chat_client, "chat_api", None)
    if callable(chat_fn):
        data = chat_fn(payload)
        msg = data.get("message") if isinstance(data.get("message"), dict) else {}
        out = _assistant_text_parts_from_ollama_message(msg if isinstance(msg, dict) else {})
        out["ollama_payload"] = data if isinstance(data, dict) else {}
        return out
    text = chat_client.chat(
        messages, model, stream=False, options=options_overlay if options_overlay else None, think=think
    )
    visible = (text or "").strip()
    return {
        "visible_content": visible,
        "reasoning_content": "",
        "final_content": visible,
        "ollama_payload": {},
    }


def _proxy_ollama_chat_text(
    chat_client: Any,
    messages: list[dict[str, Any]],
    model: str,
    think: bool | str | None,
    *,
    options_overlay: dict[str, Any] | None = None,
) -> str:
    """Non-stream /api/chat; returns merged visible assistant text (thinking + content)."""
    return _proxy_ollama_chat_text_parts(
        chat_client,
        messages,
        model,
        think,
        options_overlay=options_overlay,
    )["visible_content"]


def _iter_proxy_ollama_chat_stream(
    chat_client: Any,
    messages: list[dict[str, Any]],
    model: str,
    think: bool | str | None,
    *,
    options_overlay: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
) -> Iterator[tuple[str, Any]]:
    """Stream /api/chat; yield event tuples from ``iter_chat_api_stream_events``.

    Mirrors ``_proxy_ollama_chat_text`` but streaming.  Falls back to a single
    visible turn when the client has no streaming support.
    """
    _co = dict(getattr(chat_client, "_default_options", None) or {})
    if options_overlay:
        _co.update(options_overlay)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": dict(_co),
    }
    if think is not None:
        payload["think"] = think
    if tools:
        payload["tools"] = tools
    _tc_ollama = ollama_chat_tool_choice_payload_value(tool_choice)
    if _tc_ollama is not None:
        payload["tool_choice"] = _tc_ollama

    stream_fn = getattr(chat_client, "iter_chat_api_stream_events", None)
    if callable(stream_fn):
        yield from stream_fn(payload)
    else:
        chat_api_fn = getattr(chat_client, "chat_api", None)
        if callable(chat_api_fn):
            data = chat_api_fn(payload)
            msg = data.get("message") if isinstance(data.get("message"), dict) else {}
            parts = _assistant_text_parts_from_ollama_message(msg if isinstance(msg, dict) else {})
            if parts["reasoning_content"]:
                yield ("thinking_delta", parts["reasoning_content"])
            if parts["final_content"]:
                yield ("content_delta", parts["final_content"])
            tc = msg.get("tool_calls") if isinstance(msg, dict) else None
            if isinstance(tc, list) and tc:
                yield ("tool_calls", tc)
            yield ("done", data if isinstance(data, dict) else {})
        else:
            parts = _proxy_ollama_chat_text_parts(
                chat_client, messages, model, think, options_overlay=options_overlay,
            )
            if parts["reasoning_content"]:
                yield ("thinking_delta", parts["reasoning_content"])
            if parts["final_content"]:
                yield ("content_delta", parts["final_content"])
            elif parts["visible_content"]:
                yield ("content_delta", parts["visible_content"])
            yield ("done", {})


def _normalize_request_messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    """
    OpenAI chat uses ``messages``; some clients POST legacy ``prompt`` / ``suffix`` instead.
    Map to a single user message without model-specific fill-in-the-middle tokens.
    """
    raw = body.get("messages")
    if isinstance(raw, list) and len(raw) > 0:
        return _normalize_and_sanitize_messages(raw)

    prompt: str | None = None
    p_raw = body.get("prompt")
    if isinstance(p_raw, str):
        prompt = p_raw
    elif isinstance(p_raw, list):
        parts: list[str] = []
        for p in p_raw:
            if isinstance(p, str):
                parts.append(p)
        if parts:
            prompt = "".join(parts)

    suffix = body.get("suffix")
    suffix_s = suffix if isinstance(suffix, str) else ""

    if isinstance(prompt, str) and prompt:
        if suffix_s:
            content = f"{prompt}\n{suffix_s}"
            return [{"role": "user", "content": content}]
        return [{"role": "user", "content": prompt}]

    inp = body.get("input")
    if isinstance(inp, str) and inp.strip():
        return [{"role": "user", "content": inp}]

    return []


_VISION_READ_LOCAL_FILES = str(os.getenv("LLM_PROXY_VISION_READ_LOCAL_FILES", "0")).strip() in {
    "1",
    "true",
    "yes",
}
_VISION_ALLOW_ABS_PATHS = str(os.getenv("LLM_PROXY_VISION_ALLOW_ABS_PATHS", "0")).strip() in {
    "1",
    "true",
    "yes",
}
_COPILOT_CANNOT_READ_IMAGE_RE = re.compile(
    r'(?is)\bERROR:\s*Cannot\s+read\s+"([^"]+\.(?:png|jpe?g|webp|gif))"\s*\(this model does not support image input\)\.',
)
_IMAGE_PATH_HINT_RE = re.compile(
    r"(?is)\b(file:///[^\s\"'<>]+\.(?:png|jpe?g|webp|gif)|[A-Za-z]:[\\/][^\s\"'<>]+\.(?:png|jpe?g|webp|gif)|\./[^\s\"'<>]+\.(?:png|jpe?g|webp|gif)|\b[^\s\"'<>]+\.(?:png|jpe?g|webp|gif))\b"
)


def _mime_from_image_path(path: str) -> str | None:
    low = (path or "").lower()
    if low.endswith(".png"):
        return "image/png"
    if low.endswith(".jpg") or low.endswith(".jpeg"):
        return "image/jpeg"
    if low.endswith(".webp"):
        return "image/webp"
    if low.endswith(".gif"):
        return "image/gif"
    return None


def _workspace_root_for_vision() -> Path | None:
    try:
        return Path(__file__).resolve().parents[3]
    except Exception:
        return None


def _safe_resolve_local_image_path(hint: str) -> Path | None:
    """
    Resolve a path hint to an existing local file path.
    - By default only allows workspace-relative paths.
    - Absolute paths are allowed only when LLM_PROXY_VISION_ALLOW_ABS_PATHS=1.
    """
    h = str(hint or "").strip()
    if not h:
        return None
    if h.lower().startswith("file:///"):
        h = h[8:]  # strip file:///
    h = h.strip().strip('"').strip("'")
    if not h:
        return None

    p = Path(h)
    ws = _workspace_root_for_vision()

    candidates: list[Path] = []
    if p.is_absolute():
        if _VISION_ALLOW_ABS_PATHS:
            candidates.append(p)
    else:
        if ws is not None:
            candidates.append((ws / p).resolve())
        candidates.append(Path.cwd() / p)

    for c in candidates:
        try:
            rc = c.resolve()
        except Exception:
            continue
        if not rc.exists() or not rc.is_file():
            continue
        if not _VISION_ALLOW_ABS_PATHS and ws is not None:
            try:
                rc.relative_to(ws)
            except Exception:
                continue
        return rc
    return None


def _read_local_image_as_data_url(path: Path) -> str | None:
    mime = _mime_from_image_path(str(path))
    if not mime:
        return None
    try:
        raw = path.read_bytes()
    except Exception:
        return None
    if len(raw) > VISION_MAX_DECODED_BYTES:
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _file_hint_and_cleaned_user_text(text: str) -> tuple[str | None, str]:
    """Detect Copilot/Kilo image file hint or path; return (hint_or_none, text_after_stripping_error_line)."""
    t = (text or "").strip()
    if not t:
        return None, ""
    file_hint: str | None = None
    m = _COPILOT_CANNOT_READ_IMAGE_RE.search(t)
    if m:
        file_hint = m.group(1).strip()
        t = _COPILOT_CANNOT_READ_IMAGE_RE.sub("", t).strip()
    if file_hint is None:
        m2 = _IMAGE_PATH_HINT_RE.search(t)
        if m2:
            file_hint = m2.group(1).strip()
    return file_hint, t


def _maybe_inline_image_from_text_message(msg: dict[str, Any]) -> dict[str, Any]:
    if not _VISION_READ_LOCAL_FILES:
        return msg
    if not isinstance(msg, dict):
        return msg
    if str(msg.get("role") or "").strip() != "user":
        return msg
    content = msg.get("content")

    file_hint: str | None = None
    text_for_sanitize: str = ""

    if isinstance(content, str):
        if not str(content).strip():
            return msg
        file_hint, text_for_sanitize = _file_hint_and_cleaned_user_text(content)
    elif isinstance(content, list):
        new_parts: list[dict[str, Any]] = []
        hint_consumed = False
        for p in content:
            if not isinstance(p, dict):
                continue
            typ = p.get("type")
            if typ == "image_url":
                new_parts.append(dict(p))
                continue
            if typ == "text" or (typ is None and isinstance(p.get("text"), str)):
                tx = str(p.get("text", ""))
                if not hint_consumed:
                    h, cleaned = _file_hint_and_cleaned_user_text(tx)
                    if h:
                        file_hint = h
                        hint_consumed = True
                        new_parts.append({"type": "text", "text": cleaned})
                    else:
                        new_parts.append({"type": "text", "text": tx})
                else:
                    new_parts.append({"type": "text", "text": tx})
                continue
            try:
                dumped = json.dumps(p, ensure_ascii=False)
            except (TypeError, ValueError):
                dumped = str(p)
            new_parts.append({"type": "text", "text": dumped})
        if not file_hint:
            return msg
        p = _safe_resolve_local_image_path(file_hint)
        if p is None:
            return msg
        data_url = _read_local_image_as_data_url(p)
        if not data_url:
            return msg
        new_msg = dict(msg)
        text_blocks: list[dict[str, Any]] = []
        preserved_imgs: list[dict[str, Any]] = []
        for block in new_parts:
            if block.get("type") == "text" and str(block.get("text") or "").strip():
                text_blocks.append(block)
            elif block.get("type") == "image_url":
                preserved_imgs.append(dict(block))
        st = sanitize_openai_text_part(openai_parts_to_flat_text(text_blocks)) if text_blocks else ""
        merged: list[dict[str, Any]] = []
        if st:
            merged.append({"type": "text", "text": st})
        merged.extend(preserved_imgs)
        merged.append({"type": "image_url", "image_url": {"url": data_url}})
        new_msg["content"] = merged
        return new_msg
    else:
        return msg

    if not file_hint:
        return msg
    p = _safe_resolve_local_image_path(file_hint)
    if p is None:
        return msg
    data_url = _read_local_image_as_data_url(p)
    if not data_url:
        return msg

    new_msg = dict(msg)
    new_msg["content"] = [
        {"type": "text", "text": sanitize_openai_text_part(text_for_sanitize) if text_for_sanitize else ""},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    return new_msg


def _sanitize_message_text(text: str, *, max_chars: int = 80_000) -> str:
    """Hard-cap user/system string message size (see ``sanitize_openai_text_part``)."""
    return sanitize_openai_text_part(text, max_chars=max_chars)


def _normalize_and_sanitize_messages(raw_messages: list[Any]) -> list[dict[str, Any]]:
    """
    Normalize OpenAI chat messages into a safe shape for the proxy pipeline.

    For ``user`` messages: optional local-file inlining runs **before** inline data-URL promotion,
    then sanitization (so path/error hints still work when combined with pasted data URLs).

    - String ``content``: cap length (inline data URLs are promoted for user turns earlier in the pipeline).
    - List ``content`` (OpenAI multimodal): keep validated ``data:image`` ``image_url`` parts for
      downstream mapping to Ollama ``images``; replace unsupported URLs with short text notes.
    """
    out: list[dict[str, Any]] = []
    for m in raw_messages:
        if not isinstance(m, dict):
            continue
        nm: dict[str, Any] = dict(m)
        if str(m.get("role") or "").strip() == "user":
            nm = _maybe_inline_image_from_text_message(nm)
            nm["content"] = promote_inline_data_image_urls_in_content(nm.get("content"))
        nm["role"] = str(m.get("role") or "").strip() or "user"

        c = nm.get("content")
        if isinstance(c, list):
            nm["content"] = sanitize_proxy_content_parts(c)
        elif isinstance(c, str):
            nm["content"] = _sanitize_message_text(c)
        elif c is None:
            nm["content"] = ""
        else:
            nm["content"] = _sanitize_message_text(json.dumps(c, ensure_ascii=False))

        out.append(nm)
    return out


def run_chat_completions(
    w: LlmProxyWiring, *, body_override: dict[str, Any] | None = None
) -> Response | tuple[Response, int]:
    b = w.base
    prefix = b.prefix
    suffix = b.suffix
    webui_dir = b.webui_dir
    system_prefix = b.system_prefix
    system_suffix = b.system_suffix
    context_chunk_chars = b.context_chunk_chars
    context_total_chars = b.context_total_chars
    confidence_threshold = b.confidence_threshold
    ollama_model = b.ollama_model
    log_preview = b.log_preview
    rag_repo = b.rag_repo
    embed_provider = b.embed_provider
    rerank_client = b.rerank_client
    chat_client = b.chat_client

    start_time = time.time()
    user_query = ""
    rag_context_data = None
    latency_ms = 0
    prompt_tokens_approx = 0
    completion_tokens_approx = 0
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    trace = {
        "trace_id": trace_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request": {},
        "internet": {},
        "rag": {},
        "ollama": {},
        "response": {},
        "steps": [],
        "pipeline_steps": [],
    }
    proxy_db_path = _resolve_proxy_db_path_from_wiring(w)
    w.set_current_trace(trace)

    try:
        if body_override is not None:
            body = dict(body_override)
        else:
            body = request.get_json(force=True, silent=True) or {}
    except Exception as e:
        w.log_webui_error("rag_routes.chat_completions", e, {"stage": "parse_body"})
        _log_rag_error("parse_body", e)
        return jsonify({"error": "Invalid JSON"}), 400
    messages = _normalize_request_messages(body)
    if not messages:
        return jsonify({"error": "messages is required"}), 400
    body["messages"] = messages
    _proxy_trace_meta: dict[str, Any] | None = None
    _raw_trace_meta = body.pop("_proxy_trace_meta", None)
    if isinstance(_raw_trace_meta, dict):
        _proxy_trace_meta = dict(_raw_trace_meta)
    w.set_proxy_status(w.status_rag_search)

    proxy_settings, proxy_model_setting = _load_proxy_settings_and_model(w.get_settings_repository)

    stream = body.get("stream", False)
    chat_max_tokens: int | None = None
    _mt_raw = body.get("max_tokens")
    if _mt_raw is not None:
        try:
            _mt_n = int(_mt_raw)
            if _mt_n > 0:
                chat_max_tokens = _mt_n
        except (TypeError, ValueError):
            pass
    raw_model = body.get("model")
    if raw_model is None or not str(raw_model).strip():
        w.set_proxy_status(w.status_idle)
        return jsonify(
            {
                "error": (
                    "model is required: use an LLM Proxy build id, a concrete Ollama model tag, "
                    "or ChironAI-Autocomplete when autocomplete is configured."
                ),
            }
        ), 400
    requested_model = str(raw_model).strip()
    rt = w.runtime

    build_extra_options: dict[str, Any] = {}
    dumb_build_pipeline = False
    active_build: dict[str, Any] | None = None
    try:
        from application.llm_proxy_builds import (
            LLM_PROXY_BUILDS_APP_KEY,
            build_ollama_options,
            find_build_by_id,
            load_builds_json,
            merge_build_into_proxy_settings,
        )

        _repo_b = w.get_settings_repository()
        _builds_raw = _repo_b.get_app_setting(LLM_PROXY_BUILDS_APP_KEY)
        _all_builds = load_builds_json(_builds_raw)
        active_build = find_build_by_id(_all_builds, str(requested_model or "").strip())
    except Exception:
        active_build = None

    if active_build and str(active_build.get("backend") or "").strip().lower() == "dumb":
        proxy_settings = merge_build_into_proxy_settings(proxy_settings, active_build)
        _om_b = str(active_build.get("model") or "").strip() or str(active_build.get("ollama_model") or "").strip()
        if _om_b:
            proxy_model_setting = _om_b
        build_extra_options = build_ollama_options(active_build)
        if active_build.get("temperature") is not None:
            try:
                build_extra_options["temperature"] = float(active_build["temperature"])
            except (TypeError, ValueError):
                pass
        if active_build.get("top_p") is not None:
            try:
                build_extra_options["top_p"] = float(active_build["top_p"])
            except (TypeError, ValueError):
                pass
        dumb_build_pipeline = True
        if active_build.get("chat_think") and "think" not in body:
            body["think"] = True
        _rl_b = str(active_build.get("reasoning_level") or "").strip()
        if _rl_b and not body.get("reasoning_level") and not body.get("reasoning"):
            body["reasoning_level"] = _rl_b

    build_sse_streaming = True
    if dumb_build_pipeline and active_build:
        build_sse_streaming = active_build.get("sse_streaming", True) is not False

    def ollama_options_overlay() -> dict[str, Any] | None:
        merged: dict[str, Any] = {**build_extra_options}
        if chat_max_tokens is not None:
            merged["num_predict"] = chat_max_tokens
        return merged if merged else None

    effective_num_predict = _effective_num_predict(
        chat_client,
        build_extra_options,
        chat_max_tokens,
    )
    effective_num_ctx = _effective_num_ctx(chat_client, build_extra_options)
    input_budget = _input_budget_from_context(
        num_ctx=effective_num_ctx,
        num_predict=effective_num_predict,
    )

    private_build = bool(dumb_build_pipeline and active_build and bool(active_build.get("private")))
    if private_build:
        w.set_current_trace(None)

    def publish_trace(tr: dict[str, Any]) -> None:
        if private_build:
            w.set_current_trace(None)
        else:
            w.set_current_trace(tr)

    def publish_response_artifacts(
        *,
        visible_content: str,
        reasoning_content: str = "",
        final_content: str = "",
    ) -> None:
        if private_build:
            return
        req = trace.get("request") if isinstance(trace.get("request"), dict) else {}
        set_response_artifacts(
            trace_id=str(trace.get("trace_id") or "").strip() or None,
            client_request_id=str(req.get("client_request_id") or "").strip() or None,
            visible_content=visible_content,
            reasoning_content=reasoning_content,
            final_content=final_content,
        )

    autocomplete_id = rt.autocomplete_model_logical_id
    is_autocomplete = requested_model == autocomplete_id
    proxy_autocomplete_ollama: str | None = None
    tools = body.get("tools") if isinstance(body.get("tools"), list) else []
    tool_choice = body.get("tool_choice")
    tool_choice_effective = tool_choice if tool_choice not in (None, "") else "auto"
    if openai_tool_choice_means_none(tool_choice):
        tool_choice_effective = "none"
    testing_disable_rerank = bool(body.get("testing_disable_rerank"))
    explicit_reasoning = body.get("reasoning_level") or body.get("reasoning")
    if dumb_build_pipeline and "include_rag_metadata" not in body:
        include_rag_metadata = bool(proxy_settings.get("include_rag_metadata", False))
    else:
        include_rag_metadata = bool(body.get("include_rag_metadata", False))

    def proxy_backend_tag() -> str:
        if is_autocomplete:
            return "autocomplete"
        if dumb_build_pipeline:
            return "rag_fusion"
        return "direct"

    def persist_proxy_request_log(
        *,
        message: str,
        response_preview: str,
        latency_ms_value: int,
        trace_payload: dict[str, Any],
        stream_value: bool,
        include_rag_fields: bool,
        include_token_fields: bool,
        prompt_tokens_value: int | None = None,
        completion_tokens_value: int | None = None,
        total_tokens_value: int | None = None,
        ollama_chat_stream: bool | None = None,
        sse_single_chunk: bool = False,
        extra_metadata: dict[str, Any] | None = None,
        warn_label: str,
    ) -> None:
        if private_build:
            return
        try:
            session_manager = w.get_session_manager()
            session_manager.get_or_create_session("proxy")
            logs_repo = w.get_logs_repository()
            metadata: dict[str, Any] = {
                "user_query": user_query[:500],
                "response_preview": response_preview[:500],
                "trace_id": trace_id,
                "model": use_model,
                "latency_ms": latency_ms_value,
                "trace": trace_payload,
                "stream": bool(stream_value),
                "is_autocomplete": bool(is_autocomplete),
                "requested_model": requested_model,
                "proxy_backend": proxy_backend_tag(),
            }
            if include_rag_fields:
                metadata["rag_context"] = rag_context_data
                metadata["rag_steps"] = rag_timings
            if include_token_fields:
                metadata["prompt_tokens"] = prompt_tokens_value
                metadata["completion_tokens"] = completion_tokens_value
                metadata["total_tokens"] = total_tokens_value
            if ollama_chat_stream is not None:
                metadata["ollama_chat_stream"] = bool(ollama_chat_stream)
            if sse_single_chunk:
                metadata["sse_single_chunk"] = True
            if extra_metadata:
                metadata.update(extra_metadata)
            logs_repo.add_log(
                session_id="proxy",
                level="INFO",
                message=message,
                source="proxy",
                metadata=metadata,
            )
        except Exception as e:
            _RAG_LOG.warning("Failed to log proxy %s request to database: %s", warn_label, e)

    force_rag = bool(body.get("force_rag"))
    if is_autocomplete:
        force_rag = False
        tools = []
        body["tools"] = []
        tool_choice_effective = "none"
    has_tool_result = any(isinstance(m, dict) and m.get("role") == "tool" for m in messages)
    last_tool_content = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "tool":
            last_tool_content = str(
                m.get("content")
                or m.get("output")
                or m.get("result")
                or m.get("text")
                or ""
            )
            break
    _ltl = last_tool_content.lower()
    _tool_exit_code: int | None = None
    _tool_ok_flag: bool | None = None
    _tool_error_text: str = ""
    try:
        _parsed_tool = json.loads(last_tool_content) if last_tool_content.strip().startswith(("{", "[")) else None
        if isinstance(_parsed_tool, dict):
            if isinstance(_parsed_tool.get("ok"), bool):
                _tool_ok_flag = bool(_parsed_tool.get("ok"))
            _meta = _parsed_tool.get("metadata")
            if isinstance(_meta, dict):
                _ec = _meta.get("exit_code")
                if isinstance(_ec, (int, float)):
                    _tool_exit_code = int(_ec)
                _stderr = _meta.get("stderr")
                if isinstance(_stderr, str) and _stderr.strip():
                    _tool_error_text = _stderr.strip().lower()
            _err = _parsed_tool.get("error")
            if isinstance(_err, str) and _err.strip():
                _tool_error_text = (_tool_error_text + "\n" + _err.strip().lower()).strip()
    except Exception:
        pass
    tool_result_indicates_failure = any(
        x in _ltl
        for x in (
            "no edits were made",
            "no edits",
            "failed to receive tool input",
            "path not found",
            "can't edit file",
            "cannot edit file",
            "can't create file",
            "cannot create file",
            "parent directory doesn't exist",
            "parent directory does not exist",
            "file not found",
            "unknown variant",
        )
    )
    if not tool_result_indicates_failure and _tool_ok_flag is False:
        tool_result_indicates_failure = True
    if not tool_result_indicates_failure and _tool_exit_code is not None and _tool_exit_code != 0:
        tool_result_indicates_failure = True
    if not tool_result_indicates_failure and _tool_error_text:
        tool_result_indicates_failure = True
    if not tool_result_indicates_failure and _tool_result_looks_like_unintended_deletion(last_tool_content):
        tool_result_indicates_failure = True
    _last_msg = messages[-1] if messages else None
    _last_role = _last_msg.get("role") if isinstance(_last_msg, dict) else None
    _last_tool_idx = -1
    _last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        mi = messages[i]
        if not isinstance(mi, dict):
            continue
        r = mi.get("role")
        if _last_tool_idx < 0 and r == "tool":
            _last_tool_idx = i
        if r == "user" and _last_user_idx < 0:
            _last_user_idx = i
        if _last_tool_idx >= 0 and _last_user_idx >= 0:
            break
    # Only treat it as a "post tool success" turn when the latest message is a tool result
    # and there is NO newer user message after that tool result.
    post_tool_success_turn = bool(
        _last_role == "tool"
        and has_tool_result
        and not tool_result_indicates_failure
        and (_last_user_idx < 0 or _last_user_idx < _last_tool_idx)
    )

    if is_autocomplete:
        proxy_autocomplete_ollama = w.get_autocomplete_ollama_model()
        if not proxy_autocomplete_ollama:
            w.set_proxy_status(w.status_idle)
            return jsonify(
                {
                    "error": (
                        "LLM Proxy autocomplete is not configured: choose a concrete Ollama model "
                        "for autocomplete in WebUI (LLM Proxy → Autocomplete), or set "
                        "LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL."
                    ),
                }
            ), 400

    fetch_web_knowledge, fetch_web_knowledge_source = resolve_fetch_web_knowledge(
        request_value=body.get("fetch_web_knowledge"),
        proxy_settings=proxy_settings,
        is_autocomplete=bool(is_autocomplete),
    )

    _get_rag_prompt = w.get_rag_prompt_prefix_suffix
    rag_prompt_file_exists = w.rag_prompt_file_exists

    use_prompt_template_enabled = proxy_settings.get("use_prompt_template", True) is not False
    proxy_prompt_name_required: str | None = None
    if system_prefix is None:
        if use_prompt_template_enabled:
            _pn = str(body.get("prompt_name") or "").strip() or str(proxy_settings.get("prompt_name") or "").strip()
            if not _pn or not rag_prompt_file_exists(_pn):
                w.set_proxy_status(w.status_idle)
                return jsonify(
                    {
                        "error": (
                            "LLM Proxy is not configured: choose a valid Prompt template in WebUI "
                            "(LLM Proxy → builds or saved proxy settings). The file prompts/<name>.md must exist."
                        ),
                        "detail": f"prompt_name={_pn!r}" if _pn else "prompt_name is empty",
                    }
                ), 400
            proxy_prompt_name_required = _pn
        if dumb_build_pipeline and not proxy_model_setting:
            w.set_proxy_status(w.status_idle)
            return jsonify(
                {
                    "error": "Dumb build is missing model; edit the build in LLM Proxy (builds).",
                }
            ), 400

    last_user = w.last_user_content(messages)
    user_query = last_user  # Store for logging
    selected_edit_tool_name = _select_edit_tool_name(tools, user_query)
    selected_edit_tool = _get_tool_by_name(tools, selected_edit_tool_name) if selected_edit_tool_name else None
    selected_tool_write_capable = _tool_schema_accepts_content(selected_edit_tool)
    # If the client omitted `tools` entirely but referenced a file, assume an IDE-side `edit_file`
    # tool exists (Zed supports it) and allow emitting tool_calls anyway.
    if (not tools) and (tool_choice_effective != "none"):
        user_text = user_query or last_user or ""
        if _extract_file_path_from_user_text(user_text):
            selected_edit_tool_name = "edit_file"
            selected_edit_tool = None
            selected_tool_write_capable = True
    use_native_tools = bool(tools) and tool_choice_effective != "none"
    tool_loop_stats: dict[str, Any] | None = None
    if use_native_tools:
        tool_loop_stats = _tool_round_stats_since_last_user(messages)
    effective_max_agent_steps = _effective_max_agent_steps(active_build)
    tool_loop_limit_reached = bool(
        use_native_tools
        and effective_max_agent_steps is not None
        and tool_loop_stats is not None
        and int(tool_loop_stats.get("rounds") or 0) >= effective_max_agent_steps
    )
    if tool_loop_limit_reached:
        tools = []
        tool_choice_effective = "none"
        use_native_tools = False
    context_length = len(last_user.split())
    if system_prefix is not None:
        effective_prefix = prefix
        effective_suffix = suffix
    elif use_prompt_template_enabled:
        effective_prefix, effective_suffix = _get_rag_prompt(proxy_prompt_name_required)
    else:
        effective_prefix, effective_suffix = "", ""
    effective_context_chunk_chars = context_chunk_chars
    effective_context_total_chars = context_total_chars
    effective_confidence_threshold = confidence_threshold
    effective_rag_repo = rag_repo
    effective_embed_provider = embed_provider
    effective_base_rerank_client = rerank_client
    if is_autocomplete:
        effective_ollama_model = proxy_autocomplete_ollama or ""
    elif dumb_build_pipeline:
        effective_ollama_model = proxy_model_setting or ollama_model
    else:
        effective_ollama_model = requested_model
    reasoning_level = w.determine_reasoning_level(
        last_user, context_length, effective_ollama_model, explicit_reasoning
    )
    reasoning_for_prompt = reasoning_level

    actual_model = (
        effective_ollama_model if dumb_build_pipeline or is_autocomplete else requested_model
    )

    trace_chain_id, trace_chain_source = _resolve_trace_chain_id(
        client_request_id=body.get("client_request_id"),
        proxy_trace_meta=_proxy_trace_meta,
    )
    trace["request"] = {
        "requested_model": requested_model,
        "actual_model": actual_model,
        "proxy_pipeline": "passthrough_only",
        "stream": bool(stream),
        "build_sse_streaming": build_sse_streaming,
        "max_tokens": chat_max_tokens,
        "effective_num_predict": effective_num_predict,
        "effective_num_ctx": effective_num_ctx,
        "ollama_chat_stream": False,
        "include_rag_metadata": bool(include_rag_metadata),
        "tools_count": len(tools),
        "tools_names_preview": [n for n in (_extract_tool_name(t) for t in tools) if n][:20],
        "selected_edit_tool_name": selected_edit_tool_name,
        "selected_edit_tool_required": (
            (
                ((selected_edit_tool or {}).get("function") or {}).get("parameters") or {}
            ).get("required")
            if isinstance(selected_edit_tool, dict)
            else None
        ),
        "tool_choice": tool_choice if isinstance(tool_choice, (str, dict)) else None,
        "tool_choice_effective": tool_choice_effective
        if isinstance(tool_choice_effective, (str, dict))
        else str(tool_choice_effective),
        "has_tool_result": bool(has_tool_result),
        "tool_result_indicates_failure": bool(tool_result_indicates_failure),
        "post_tool_success_turn": bool(post_tool_success_turn),
        "tool_result_last_content_preview": (last_tool_content[:240] if last_tool_content else ""),
        "force_rag": bool(force_rag),
        "fetch_web_knowledge": bool(fetch_web_knowledge),
        "fetch_web_knowledge_source": fetch_web_knowledge_source,
        "reasoning_level": explicit_reasoning or reasoning_level,
        "reasoning_for_prompt": reasoning_for_prompt,
        "user_query_preview": (user_query or "")[:500],
        "is_autocomplete": bool(is_autocomplete),
        "testing_disable_rerank": bool(testing_disable_rerank),
        "client_request_id": str(body.get("client_request_id") or "").strip() or None,
    }
    if input_budget is not None:
        trace["request"]["input_budget"] = dict(input_budget)
    if effective_max_agent_steps is not None:
        trace["request"]["effective_max_agent_steps"] = effective_max_agent_steps
    if tool_loop_limit_reached:
        trace["request"]["tool_loop_limit_reached"] = True
        trace["request"]["tools_suppressed_for_step_limit"] = True
        _append_trace_warning(trace, "tool_loop_limit_reached")
    if trace_chain_id:
        trace["request"]["trace_chain_id"] = trace_chain_id
        trace["request"]["trace_chain_source"] = trace_chain_source
    if tool_loop_stats is not None:
        trace["request"]["tool_loop_stats"] = tool_loop_stats
    if _proxy_trace_meta:
        for _k, _v in _proxy_trace_meta.items():
            if _k in ("proxy_v1_route", "responses_client_stream", "incoming_request_id"):
                trace["request"][_k] = _v
    if body.get("tools_count_raw") is not None:
        trace["request"]["tools_count_raw"] = body.get("tools_count_raw")
    if body.get("tools_count_normalized") is not None:
        trace["request"]["tools_count_normalized"] = body.get("tools_count_normalized")
    if isinstance(body.get("tools_types_raw"), list):
        trace["request"]["tools_types_raw"] = body.get("tools_types_raw")
    if isinstance(body.get("tools_types_dropped"), list):
        trace["request"]["tools_types_dropped"] = body.get("tools_types_dropped")
    if isinstance(body.get("tools_types_normalized"), list):
        trace["request"]["tools_types_normalized"] = body.get("tools_types_normalized")
    if body.get("tool_choice_raw") is not None:
        trace["request"]["tool_choice_raw"] = body.get("tool_choice_raw")
    if body.get("tool_choice_normalized") is not None:
        trace["request"]["tool_choice_normalized"] = body.get("tool_choice_normalized")

    # IDE-independent mode: do not fail fast solely on schema checks.
    # Some clients expose incomplete tool schemas but still accept write payloads at runtime.

    # Optional project_context: frameworks list -> fresh collection names for RAG filter, and needs_refresh for background index
    project_context = body.get("project_context")
    project_fresh_collection_names: set[str] | None = None
    needs_refresh: list[tuple[str, str]] = []  # (framework_id_lower, collection_name); also filled from resolved sources below
    if (
        fetch_web_knowledge
        and isinstance(project_context, dict)
        and w.external_docs.available
        and w.external_docs.load_rag_sources_config
    ):
        frameworks = project_context.get("frameworks") or []
        if frameworks:
            rag_sources_config = w.external_docs.load_rag_sources_config()
            # Map framework name (e.g. "Alamofire") -> collection_name from config
            name_to_collection: dict[str, str] = {}
            for cfg in rag_sources_config:
                for kw in (cfg.trigger_keywords or []):
                    name_to_collection[(kw or "").strip().lower()] = cfg.collection_name
                if (cfg.external_source_id or "").strip():
                    name_to_collection[(cfg.external_source_id or "").strip().lower()] = cfg.collection_name
            ttl_days = w.get_framework_collection_ttl_days()
            settings_repo = None
            try:
                settings_repo = w.get_settings_repository()
                ttl_raw = settings_repo.get_app_setting("framework_collection_ttl_days")
                if ttl_raw is not None and str(ttl_raw).strip() != "":
                    try:
                        ttl_days = int(ttl_raw)
                    except (TypeError, ValueError):
                        pass
            except Exception:
                pass
            fresh_collections: list[str] = []
            needs_refresh.clear()
            for fw in frameworks:
                if not isinstance(fw, dict):
                    continue
                name = (fw.get("name") or "").strip()
                if not name:
                    continue
                coll = name_to_collection.get(name.lower())
                if not coll:
                    continue
                meta = None
                if settings_repo:
                    try:
                        meta = settings_repo.get_collection_meta(coll)
                    except Exception:
                        pass
                if w.check_collection_freshness(meta, ttl_days) == "fresh":
                    if coll not in fresh_collections:
                        fresh_collections.append(coll)
                else:
                    needs_refresh.append((name.lower(), coll))
            project_fresh_collection_names = set(fresh_collections) if fresh_collections else None

    # Resolve collection in priority order:
    # 1) request body collection_name
    # 2) app_settings.rag_collection
    # 3) proxy_settings.rag_collection (backward-compatible / single blob settings)
    # 4) default wiring (collection file/config) when none are set
    try:
        settings_repo = w.get_settings_repository()
    except Exception:
        settings_repo = None
    if settings_repo is not None:
        request_collection, collection_source = resolve_rag_collection(
            request_collection=(body.get("collection_name") or "").strip() or None,
            settings_repo=settings_repo,
            proxy_settings=proxy_settings,
            app_key=RAG_COLLECTION_APP_SETTING,
        )
    else:
        request_collection = (body.get("collection_name") or "").strip() or None
        collection_source = "request" if request_collection else "default"
    if request_collection and not is_autocomplete:
        req_params, req_deps = w.get_rag_answer_params(
            webui_dir=webui_dir,
            collection_name=request_collection,
        )
        if system_prefix is not None:
            effective_prefix = system_prefix
            effective_suffix = system_suffix if system_suffix is not None else req_params.system_suffix
        elif not use_prompt_template_enabled:
            effective_prefix = ""
            effective_suffix = ""
        effective_context_chunk_chars = req_params.context_chunk_chars
        effective_context_total_chars = req_params.context_total_chars
        effective_confidence_threshold = req_params.confidence_threshold
        effective_ollama_model = req_params.model_name
        effective_rag_repo = req_deps.rag_repo
        effective_embed_provider = req_deps.embed_provider
        effective_base_rerank_client = req_deps.rerank_client
        if dumb_build_pipeline and proxy_model_setting:
            effective_ollama_model = proxy_model_setting
        actual_model = (
            effective_ollama_model if dumb_build_pipeline or is_autocomplete else requested_model
        )
        trace["request"]["actual_model"] = actual_model
        trace["request"]["collection_name"] = request_collection
        trace["request"]["collection_source"] = collection_source
        trace["request"]["legacy_collection_fallback_used"] = collection_source == "proxy_settings.rag_collection"
    else:
        trace["request"]["collection_source"] = "default"

    if is_autocomplete:
        effective_ollama_model = proxy_autocomplete_ollama or effective_ollama_model
    if dumb_build_pipeline and proxy_model_setting:
        effective_ollama_model = proxy_model_setting
    actual_model = (
        effective_ollama_model if dumb_build_pipeline or is_autocomplete else requested_model
    )
    trace["request"]["actual_model"] = actual_model

    # Collection resolution can reload proxy_settings from DB and drop the dumb-build merge;
    # re-apply build overlay so per-build RAG limits and rag_collection stay authoritative.
    if dumb_build_pipeline and active_build:
        try:
            from application.llm_proxy_builds import merge_build_into_proxy_settings as _merge_build_ps

            proxy_settings = _merge_build_ps(dict(proxy_settings), active_build)
        except Exception:
            pass

    _cco = _proxy_settings_optional_int(proxy_settings, "context_chunk_chars", 64, 500_000)
    if _cco is not None:
        effective_context_chunk_chars = _cco
    _cto = _proxy_settings_optional_int(proxy_settings, "context_total_chars", 256, 2_000_000)
    if _cto is not None:
        effective_context_total_chars = _cto
    effective_rag_top_k = _proxy_settings_optional_int(proxy_settings, "rag_top_k", 1, 256)
    trace["request"]["effective_context_chunk_chars"] = effective_context_chunk_chars
    trace["request"]["effective_context_total_chars"] = effective_context_total_chars
    if effective_rag_top_k is not None:
        trace["request"]["rag_top_k"] = effective_rag_top_k

    # Keep embed model in sync with WebUI setting for /v1 path as well.
    # This avoids accidental model="" calls to /api/embed when env defaults are empty.
    try:
        settings_repo = w.get_settings_repository()
        selected_embed_model = str(settings_repo.get_app_setting("rag_embed_model") or "").strip()
        current_embed_model = str(
            getattr(effective_embed_provider, "_model", None)
            or getattr(effective_embed_provider, "model", None)
            or ""
        ).strip()
        target_embed_model = selected_embed_model or current_embed_model or str(effective_ollama_model or "").strip()
        if target_embed_model:
            if hasattr(effective_embed_provider, "_model"):
                setattr(effective_embed_provider, "_model", target_embed_model)
            elif hasattr(effective_embed_provider, "model"):
                setattr(effective_embed_provider, "model", target_embed_model)
            if target_embed_model != current_embed_model:
                trace["request"]["embed_model_override"] = target_embed_model
    except Exception:
        pass

    _ollama_caps: frozenset[str] | None = None
    try:
        _chat_u = getattr(chat_client, "_url", None)
        if isinstance(_chat_u, str) and _chat_u.strip() and (effective_ollama_model or "").strip():
            _ollama_caps = get_cached_ollama_capabilities(effective_ollama_model.strip(), _chat_u.strip())
            if _ollama_caps is not None and use_native_tools and not caps_supports_tools(_ollama_caps):
                use_native_tools = False
    except Exception:
        _ollama_caps = None

    ollama_think = effective_ollama_think_from_body(
        body, effective_ollama_model, capabilities=_ollama_caps
    )
    trace["request"]["ollama_think"] = ollama_think
    if _ollama_caps is not None:
        trace["request"]["ollama_capabilities"] = sorted(_ollama_caps)
    trace["request"]["use_native_tools"] = use_native_tools

    effective_base_rerank_client = _apply_selected_rerank_model(
        effective_base_rerank_client,
        proxy_settings,
        trace,
    )

    # Proxy: do not read settings from DB; rerank is configurable via proxy_rerank_enabled.
    effective_rerank_client = (
        effective_base_rerank_client
        if (w.get_proxy_rerank_enabled() and not testing_disable_rerank)
        else None
    )
    rag_keywords = w.get_rag_required_keywords()

    # Skip embed/search/rerank when the client is doing a local selection-based edit (typical Zed flow).
    # Model Tester feels faster largely because use_rag=false avoids this entire retrieval stack.
    explicit_skip_rag = bool(body.get("skip_rag"))
    doc_refactor_intent = _workspace_doc_refactor_intent(last_user or "")
    doc_refactor_skip = bool(doc_refactor_intent and not force_rag)
    trace["request"]["doc_refactor_intent"] = bool(doc_refactor_intent)
    trace["request"]["doc_refactor_skip"] = bool(doc_refactor_skip)
    local_tool_edit_fast_path = (
        bool(tools)
        and bool(selected_edit_tool_name)
        and tool_choice_effective != "none"
        and not use_native_tools
        and not force_rag
        and not fetch_web_knowledge
        and not request_collection
        and (
            post_tool_success_turn
            or (
                bool(_extract_file_path_from_user_text(last_user or ""))
                and _extract_line_span_from_user_text(last_user or "") is not None
            )
        )
    )
    skip_rag_retrieval = (
        explicit_skip_rag
        or local_tool_edit_fast_path
        or is_autocomplete
        or doc_refactor_skip
        or (dumb_build_pipeline and not bool(proxy_settings.get("rag_enabled", True)))
    )
    trace["request"]["skip_rag_retrieval"] = bool(skip_rag_retrieval)

    # Build RAG context: multi-collection (external_docs_rag) when triggered, else single collection
    rag_ctx_for_log = None
    rag_timings: dict[str, float] = {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0}
    background_refresh_started = False
    trace["internet"] = {"background_refresh_started": False}
    try:
        if skip_rag_retrieval:
            rag_ctx_for_log = w.rag_context_factory(
                context_text="", chunks_info=[], max_score=0.0, retrieval_skipped=True
            )
            trace["rag"]["retrieval_skipped"] = True
        else:
            trace["rag"]["retrieval_skipped"] = False

        merged_step_status = "disabled"
        merged_step_reason: str | None = None
        if not skip_rag_retrieval:
            merged_step = run_merged_docs_step(
                w=w,
                last_user=last_user,
                messages=messages,
                body=body,
                fetch_web_knowledge=bool(fetch_web_knowledge),
                request_collection=request_collection,
                effective_embed_provider=effective_embed_provider,
                effective_context_chunk_chars=effective_context_chunk_chars,
                effective_context_total_chars=effective_context_total_chars,
                project_fresh_collection_names=project_fresh_collection_names,
                needs_refresh=needs_refresh,
                logger=_RAG_LOG,
            )
            merged_step_status = merged_step.status
            merged_step_reason = merged_step.reason
            background_refresh_started = bool(merged_step.background_refresh_started)
            trace["internet"]["background_refresh_started"] = background_refresh_started
            if merged_step.used and merged_step.rag_ctx_for_log is not None:
                rag_ctx_for_log = merged_step.rag_ctx_for_log
                rag_timings = merged_step.rag_timings
            else:
                rag_ctx_for_log, rag_timings = w.build_rag_context(
                    last_user,
                    effective_rag_repo,
                    effective_embed_provider,
                    effective_rerank_client,
                    effective_context_chunk_chars,
                    effective_context_total_chars,
                    top_k=effective_rag_top_k,
                    rag_required_keywords=rag_keywords,
                    trigger_threshold=None,
                    force_rag=force_rag,
                )
        else:
            merged_step_status = "skipped"
            merged_step_reason = "rag_retrieval_skipped"
        _append_pipeline_step_trace(
            trace,
            step_id="merged_docs",
            status=merged_step_status,
            reason=merged_step_reason,
        )
        if rag_timings:
            w.set_latest_request_rag_steps(rag_timings)
            if not private_build:
                _RAG_LOG.debug(
                    "RAG steps embed_s=%.2f search_s=%.2f rerank_s=%.2f fetch_s=%.2f discovery_s=%.2f total_rag_s=%.2f",
                    rag_timings.get("embed_s", 0),
                    rag_timings.get("search_s", 0),
                    rag_timings.get("rerank_s", 0),
                    rag_timings.get("fetch_s", 0),
                    rag_timings.get("discovery_s", 0),
                    rag_timings.get("total_rag_s", 0),
                )
        if rag_ctx_for_log:
            rag_context_data = {
                "chunks_count": len(rag_ctx_for_log.chunks_info),
                "max_score": rag_ctx_for_log.max_score,
                "context_length": len(rag_ctx_for_log.context_text),
                "chunks_info": rag_ctx_for_log.chunks_info[:5] if rag_ctx_for_log.chunks_info else [],
            }
        else:
            rag_context_data = None
        
        # Enrich trace for the UI
        trace["rag"]["timings"] = dict(rag_timings or {})
        trace["internet"].update(
            {
                "fetch_s": float((rag_timings or {}).get("fetch_s", 0.0) or 0.0),
                "discovery_s": float((rag_timings or {}).get("discovery_s", 0.0) or 0.0),
            }
        )
        trace["internet"]["used"] = bool(
            (rag_timings or {}).get("fetch_s")
            or (rag_timings or {}).get("discovery_s")
            or background_refresh_started
        )
        if rag_ctx_for_log:
            trace["rag"]["context"] = {
                "context_chars_used": len(rag_ctx_for_log.context_text or ""),
                "context_budget_chars": int(effective_context_total_chars or 0),
                "context_text_preview": (rag_ctx_for_log.context_text or "")[:2000],
                "chunks": rag_ctx_for_log.chunks_info[:20] if rag_ctx_for_log.chunks_info else [],
            }
            trace["rag"]["tokens_estimates"] = {
                "embed_tokens_in": rag_timings.get("embed_tokens_in"),
                "rerank_prompt_tokens_in": rag_timings.get("rerank_prompt_tokens_in"),
                "fetch_tokens_in": rag_timings.get("fetch_tokens_in"),
                "discovery_tokens_in": rag_timings.get("discovery_tokens_in"),
            }
        else:
            trace["rag"]["context"] = None

        # RAG sub-steps (timeline for the UI)
        _rt = rag_timings or {}
        _steps: list[dict[str, object]] = []

        def _add_step(name: str, dur_s: float, tokens_in_est: object | None = None) -> None:
            if dur_s and dur_s > 0:
                _steps.append(
                    {
                        "name": name,
                        "duration_ms": int(dur_s * 1000),
                        "tokens_in_est": tokens_in_est,
                        "tokens_out_est": 0,
                    }
                )

        _add_step("embed", float(_rt.get("embed_s", 0.0) or 0.0), _rt.get("embed_tokens_in"))
        _add_step("search", float(_rt.get("search_s", 0.0) or 0.0), None)
        _add_step("rerank", float(_rt.get("rerank_s", 0.0) or 0.0), _rt.get("rerank_prompt_tokens_in"))
        _add_step("fetch", float(_rt.get("fetch_s", 0.0) or 0.0), _rt.get("fetch_tokens_in"))
        _add_step("discovery", float(_rt.get("discovery_s", 0.0) or 0.0), _rt.get("discovery_tokens_in"))
        _add_step("total_rag", float(_rt.get("total_rag_s", 0.0) or 0.0), None)
        trace["steps"] = _steps
        publish_trace(trace)
    except Exception as e:
        if not private_build:
            _RAG_LOG.warning("Failed to build RAG context for logging: %s", e)
        rag_context_data = None
    w.set_proxy_status(w.status_preparing_response)

    web_supplement_text: str | None = None
    web_sup_meta: dict[str, Any] = {
        "trigger": "none",
        "used": False,
        "error": None,
        "duration_ms": 0,
        "snippets_chars": 0,
    }
    web_step = run_web_supplement_step(
        w=w,
        is_autocomplete=bool(is_autocomplete),
        doc_refactor_skip=bool(doc_refactor_skip),
        last_user=last_user or "",
        rag_ctx_for_log=rag_ctx_for_log,
        effective_confidence_threshold=float(effective_confidence_threshold),
        proxy_settings={str(k): v for k, v in (proxy_settings or {}).items()},
    )
    web_supplement_text = web_step.text
    web_sup_meta = dict(web_step.meta or {})
    trace["internet"]["web_supplement"] = {
        "used": bool(web_sup_meta.get("used")),
        "trigger": web_sup_meta.get("trigger"),
        "error": web_sup_meta.get("error"),
        "duration_ms": web_sup_meta.get("duration_ms", 0),
        "snippets_chars": web_sup_meta.get("snippets_chars", 0),
        "queries": web_sup_meta.get("queries") or [],
        "cache_hit": bool(web_sup_meta.get("cache_hit")),
        "fetch_used": bool(web_sup_meta.get("fetch_used")),
        "wikipedia_used": bool(web_sup_meta.get("wikipedia_used")),
        "ddg_news": bool(web_sup_meta.get("ddg_news")),
        "domains_top": web_sup_meta.get("domains_top") or [],
        "snippets_count": int(web_sup_meta.get("snippets_count") or 0),
    }
    trace["internet"]["used"] = bool(
        trace["internet"].get("used") or trace["internet"]["web_supplement"].get("used")
    )
    _append_pipeline_step_trace(
        trace,
        step_id="web_supplement",
        status=web_step.status,
        reason=web_step.reason,
    )
    publish_trace(trace)

    # Reuse the same RAG context for messages (single RAG call per request)
    rag_ctx = rag_ctx_for_log if (include_rag_metadata and rag_ctx_for_log) else None
    try:
        req = w.rag_question_request_factory(
            messages=messages,
            model=actual_model,  # Use actual_model instead of requested_model
            stream=stream,
            reasoning_level=reasoning_for_prompt,
        )
        ollama_messages, use_model = w.prepare_ollama_messages(
            req,
            effective_rag_repo,
            effective_embed_provider,
            effective_rerank_client,
            effective_prefix,
            effective_suffix,
            effective_context_chunk_chars,
            effective_context_total_chars,
            effective_confidence_threshold,
            effective_ollama_model,
            reasoning_level=reasoning_for_prompt,
            rag_required_keywords=rag_keywords,
            rag_context=rag_ctx_for_log,
            trigger_threshold=None,
            force_rag=force_rag,
            native_tools=use_native_tools,
            web_supplement=web_supplement_text,
        )
        if use_model == autocomplete_id:
            use_model = effective_ollama_model

        if tool_loop_limit_reached:
            ollama_messages = [
                *ollama_messages,
                {
                    "role": "system",
                    "content": (
                        "The configured max_agent_steps limit has been reached for this turn. "
                        "Do not call tools. Summarize what is known and provide the best final answer now."
                    ),
                },
            ]

        if input_budget is not None:
            try:
                _upstream_cap_raw = os.getenv(
                    "LLM_PROXY_UPSTREAM_MESSAGES_JSON_CAP", "380000"
                ).strip()
                _upstream_json_cap = int(_upstream_cap_raw)
            except (TypeError, ValueError):
                _upstream_json_cap = 380_000
            _upstream_json_cap = max(160_000, min(_upstream_json_cap, 2_000_000))
            _budget_json_cap = min(
                _upstream_json_cap,
                int(input_budget.get("input_budget_json_chars") or _upstream_json_cap),
            )
            ollama_messages, compact_diag = _compact_upstream_messages_for_budget(
                ollama_messages,
                budget_json_chars=_budget_json_cap,
            )
            compact_diag["reserved_output_tokens"] = input_budget["reserved_output_tokens"]
            compact_diag["safety_margin_tokens"] = input_budget["safety_margin_tokens"]
            compact_diag["input_budget_tokens"] = input_budget["input_budget_tokens"]
            if compact_diag.get("compacted") or compact_diag.get("still_over_budget_after_history_compaction"):
                trace["request"]["upstream_context_compaction"] = compact_diag

        trace["ollama"]["model"] = use_model
        trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(ollama_messages)
        trace["ollama"]["think"] = ollama_think
        trace["ollama"]["chat_stream"] = False
        client_visible_model = requested_model if dumb_build_pipeline else use_model
    except Exception as e:
        if not private_build:
            w.log_webui_error("rag_routes.chat_completions", e, {"stage": "prepare_rag"})
        _log_rag_error_private("prepare_rag", e, private_build=private_build)
        return jsonify({"error": str(e)}), 500

    if use_native_tools:
        from infrastructure.ollama.openai_ollama_tool_bridge import (
            ollama_message_to_openai_assistant,
            ollama_tools_from_openai,
        )

        trace["request"]["native_tools"] = True
        native_tools_diag: dict[str, Any] = {}
        native_tools_input = list(tools)
        native_tools_input, interpolation_diag = _interpolate_native_tools_for_gemini(
            native_tools_input,
            model_name=use_model,
        )
        if interpolation_diag:
            native_tools_diag.update(interpolation_diag)
        native_tools_payload, tools_diag = _preflight_native_tools_payload(native_tools_input)
        if tools_diag:
            native_tools_diag.update(tools_diag)
        oll_tools = ollama_tools_from_openai(native_tools_payload)
        native_ollama_messages, messages_diag = _preflight_native_tool_messages(
            ollama_messages,
            model_name=use_model,
            trace_id=trace_id,
            db_path=proxy_db_path,
        )
        if messages_diag:
            native_tools_diag.update(messages_diag)

        try:
            _upstream_cap_raw = os.getenv(
                "LLM_PROXY_UPSTREAM_MESSAGES_JSON_CAP", "380000"
            ).strip()
            _upstream_json_cap = int(_upstream_cap_raw)
        except (TypeError, ValueError):
            _upstream_json_cap = 380_000
        _upstream_json_cap = max(160_000, min(_upstream_json_cap, 2_000_000))
        if input_budget is not None:
            _upstream_json_cap = min(
                _upstream_json_cap,
                int(input_budget.get("input_budget_json_chars") or _upstream_json_cap),
            )

        native_ollama_messages, compact_diag = _compact_upstream_messages_for_budget(
            native_ollama_messages,
            budget_json_chars=_upstream_json_cap,
        )
        if input_budget is not None:
            compact_diag["reserved_output_tokens"] = input_budget["reserved_output_tokens"]
            compact_diag["safety_margin_tokens"] = input_budget["safety_margin_tokens"]
            compact_diag["input_budget_tokens"] = input_budget["input_budget_tokens"]
        if compact_diag.get("compacted") or compact_diag.get("still_over_budget_after_history_compaction"):
            native_tools_diag["upstream_context_compaction"] = compact_diag

        native_ollama_messages_for_upstream = native_ollama_messages
        trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(native_ollama_messages_for_upstream)
        trace["ollama"]["tools"] = list(oll_tools) if isinstance(oll_tools, list) else []
        if (
            has_tool_result
            and not tool_result_indicates_failure
            and _tool_loop_needs_finalize_nudge(tool_loop_stats)
        ):
            native_ollama_messages = [
                *native_ollama_messages,
                {
                    "role": "system",
                    "content": (
                        "You have already completed multiple consecutive tool rounds of the same type. "
                        "Prefer synthesizing the final answer now, and call another tool only if a concrete blocker remains."
                    ),
                },
            ]
            native_tools_diag["tool_loop_finalize_nudge"] = True
            native_ollama_messages_for_upstream = native_ollama_messages
            trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(native_ollama_messages_for_upstream)
        if native_tools_diag:
            trace["request"]["native_tools_preflight"] = native_tools_diag

        # ------------------------------------------------------------------ #
        #  STREAMING native tools: true token-by-token SSE                    #
        # ------------------------------------------------------------------ #
        if stream and build_sse_streaming:
            w.set_proxy_status(w.status_response)
            trace["request"]["ollama_stream_timeout_disabled"] = True

            def generate_sse_native():
                oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                stream_start_time = time.time()
                visible_content_parts: list[str] = []
                reasoning_content_parts: list[str] = []
                final_content_parts: list[str] = []
                tool_calls_raw: list[dict[str, Any]] = []
                ollama_done_reason: str | None = None
                ollama_done_payload: dict[str, Any] | None = None
                total_tokens_holder = [0]

                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

                try:
                    for kind, data in _iter_proxy_ollama_chat_stream(
                        chat_client, native_ollama_messages, use_model, ollama_think,
                        options_overlay=ollama_options_overlay(),
                        tools=oll_tools,
                        tool_choice=tool_choice_effective,
                    ):
                        if kind in ("thinking_delta", "content_delta") and data:
                            text_part = str(data)
                            visible_content_parts.append(text_part)
                            if kind == "thinking_delta":
                                reasoning_content_parts.append(text_part)
                            else:
                                final_content_parts.append(text_part)
                            yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': data}, 'finish_reason': None}]})}\n\n"
                        elif kind == "tool_calls" and data:
                            tool_calls_raw = data
                        elif kind == "done" and isinstance(data, dict):
                            ollama_done_payload = data
                            ollama_done_reason = data.get("done_reason")
                        elif kind == "error":
                            err_text = f"[Error: {data}]"
                            visible_content_parts.append(err_text)
                            final_content_parts.append(err_text)
                            yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': err_text}, 'finish_reason': None}]})}\n\n"
                            break
                except Exception as exc:
                    if not private_build:
                        w.log_webui_error("rag_routes.chat_completions", exc, {"stage": "native_tools_stream"})
                    _log_rag_error_private("native_tools_stream", exc, private_build=private_build)
                    err_text = f"[Error: {exc}]"
                    visible_content_parts.append(err_text)
                    final_content_parts.append(err_text)
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': err_text}, 'finish_reason': None}]})}\n\n"

                full_content = "".join(visible_content_parts)
                reasoning_content = "".join(reasoning_content_parts)
                final_content = "".join(final_content_parts)
                stream_latency_ms = int((time.time() - stream_start_time) * 1000)
                budget_error = _output_budget_exhaustion_error(trace, ollama_done_payload)
                if budget_error and not tool_calls_raw:
                    visible_content_parts.append(budget_error)
                    final_content_parts.append(budget_error)
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': budget_error}, 'finish_reason': None}]})}\n\n"
                    full_content = "".join(visible_content_parts)
                    final_content = "".join(final_content_parts)

                if tool_calls_raw:
                    fake_msg: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls_raw}
                    if full_content:
                        fake_msg["content"] = full_content
                    openai_mapped = ollama_message_to_openai_assistant(fake_msg)
                    mapped_calls = openai_mapped.get("tool_calls") or []
                    gemini_upserted = _persist_gemini_tool_calls_state(
                        tool_calls=mapped_calls,
                        model_name=use_model,
                        trace_id=trace_id,
                        db_path=proxy_db_path,
                    )
                    finish_reason = "tool_calls"
                    if mapped_calls:
                        payload_calls = _sse_tool_calls_payload(mapped_calls)
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'tool_calls': payload_calls}, 'finish_reason': None}]})}\n\n"
                else:
                    gemini_upserted = 0
                    finish_reason = openai_finish_reason_from_ollama(
                        {}, ollama_done_reason=ollama_done_reason,
                    )
                    if budget_error:
                        finish_reason = "length"

                _finish_payload = f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}]})}\n\n"
                try:
                    yield _finish_payload
                    yield "data: [DONE]\n\n"
                except Exception:
                    try:
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                        yield "data: [DONE]\n\n"
                    except Exception:
                        pass

                _pt = max(1, int(len(json.dumps(native_ollama_messages_for_upstream, ensure_ascii=False)) / 4))
                _ct = max(1, int(len(full_content) / 4))
                total_tokens_holder[0] = _pt + _ct

                trace["ollama"]["chat_stream"] = True
                trace["ollama"]["tokens_estimates"] = {
                    "prompt_tokens_estimated": _pt,
                    "completion_tokens_estimated": _ct,
                    "total_tokens_estimated": total_tokens_holder[0],
                }
                trace["response"] = {
                    "latency_ms": stream_latency_ms,
                    "tool_calls_count": len(tool_calls_raw),
                    "native_tools": True,
                    **_trace_ollama_api_metrics(ollama_done_payload, model_id=use_model),
                }
                _apply_trace_response_text_fields(
                    trace["response"],
                    visible_content=full_content,
                    reasoning_content=reasoning_content,
                    final_content=final_content,
                    log_preview=log_preview,
                )
                _apply_response_diagnostics(trace)
                if gemini_upserted:
                    trace["response"]["gemini_tool_state_upserted_count"] = int(gemini_upserted)
                if tool_calls_raw:
                    trace["response"]["tool_calls_raw"] = tool_calls_raw
                trace["steps"].append({
                    "name": "provider_chat_native_tools_stream",
                    "duration_ms": stream_latency_ms,
                    "tokens_in_est": _pt,
                    "tokens_out_est": _ct,
                })
                publish_response_artifacts(
                    visible_content=full_content,
                    reasoning_content=reasoning_content,
                    final_content=final_content,
                )
                publish_trace(trace)

                if not private_build:
                    persist_proxy_request_log(
                        message=f"Proxy request (native tools stream): {user_query[:100]}...",
                        response_preview=full_content,
                        latency_ms_value=stream_latency_ms,
                        trace_payload=trace,
                        stream_value=True,
                        include_rag_fields=True,
                        include_token_fields=True,
                        prompt_tokens_value=_pt,
                        completion_tokens_value=_ct,
                        total_tokens_value=total_tokens_holder[0],
                        ollama_chat_stream=True,
                        warn_label="native-tools stream",
                    )
                    _RAG_LOG.debug(
                        json.dumps(
                            _rag_request_completed_payload(
                                user_query=user_query,
                                trace_id=trace_id,
                                use_model=use_model,
                                requested_model=requested_model,
                                latency_ms=stream_latency_ms,
                                prompt_tokens=_pt,
                                completion_tokens=_ct,
                                rag_context_for_obs=rag_ctx_for_log,
                                rag_timings=rag_timings,
                                trace=trace,
                                stream=True,
                                is_autocomplete=bool(is_autocomplete),
                                native_tools=True,
                            )
                        )
                    )

                w.set_proxy_status(w.status_idle)
                w.set_latest_request_seconds(time.time() - start_time)
                w.set_latest_request_total_tokens(total_tokens_holder[0])

            return Response(
                generate_sse_native(),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        # ------------------------------------------------------------------ #
        #  NON-STREAMING native tools (existing retry cascade)                #
        # ------------------------------------------------------------------ #
        _co = dict(getattr(chat_client, "_default_options", None) or {})
        _oo = ollama_options_overlay()
        if _oo:
            _co.update(_oo)
        body_ollama: dict[str, object] = {
            "model": use_model,
            "messages": native_ollama_messages_for_upstream,
            "stream": False,
            "options": dict(_co),
        }
        if ollama_think is not None:
            body_ollama["think"] = ollama_think
        if oll_tools:
            body_ollama["tools"] = oll_tools
        _tc_native = ollama_chat_tool_choice_payload_value(tool_choice_effective)
        if _tc_native is not None:
            body_ollama["tool_choice"] = _tc_native

        w.set_proxy_status(w.status_response)
        _native_err: str | None = None
        data: dict[str, object] = {}
        try:
            chat_fn = getattr(chat_client, "chat_api", None)
            if callable(chat_fn):
                attempt: dict[str, object] = dict(body_ollama)
                last_exc: Exception | None = None
                data = {}
                for _ in range(3):
                    try:
                        data = chat_fn(attempt)
                        last_exc = None
                        break
                    except Exception as e:
                        last_exc = e
                        if chat_error_suggests_no_tools(e) and "tools" in attempt:
                            attempt.pop("tools", None)
                            attempt.pop("tool_choice", None)
                            trace["request"]["native_tools_fallback"] = "stripped_tools_unsupported"
                            continue
                        if chat_error_suggests_no_think(e) and "think" in attempt:
                            attempt.pop("think", None)
                            trace["request"]["native_think_fallback"] = "stripped_unsupported"
                            continue
                        break
                if last_exc is not None:
                    raise last_exc
            else:
                msg_only = chat_client.chat(
                    native_ollama_messages,
                    use_model,
                    stream=False,
                    options=ollama_options_overlay(),
                    think=ollama_think,
                )
                data = {"message": {"role": "assistant", "content": msg_only}}
        except Exception as e:
            if not private_build:
                meta: dict[str, Any] = {"stage": "native_tools_ollama"}
                if native_tools_diag:
                    meta["native_tools_diag"] = native_tools_diag
                w.log_webui_error("rag_routes.chat_completions", e, meta)
            _log_rag_error_private("native_tools_ollama", e, private_build=private_build)
            _native_err = str(e)
        finally:
            w.set_proxy_status(w.status_idle)
            w.set_latest_request_seconds(time.time() - start_time)

        if _native_err:
            return jsonify({"error": _native_err}), 500

        err_obj = data.get("error")
        if err_obj:
            return jsonify({"error": str(err_obj)}), 502

        if not data:
            return jsonify(
                {"error": "Empty response from Ollama (stream or connection closed without data)"}
            ), 502

        oll_msg = data.get("message") if isinstance(data.get("message"), dict) else {}
        if not oll_msg and not err_obj:
            return jsonify(
                {
                    "error": "Ollama returned no assistant message",
                    "detail": json.dumps(data, ensure_ascii=False)[:800],
                }
            ), 502
        openai_msg = ollama_message_to_openai_assistant(oll_msg)
        finish = openai_finish_reason_from_ollama(
            oll_msg, ollama_done_reason=data.get("done_reason"),
        )
        tool_calls_out = openai_msg.get("tool_calls") if isinstance(openai_msg.get("tool_calls"), list) else []
        tool_calls_out, shell_sanitize_count = _sanitize_outgoing_shell_tool_calls(tool_calls_out)
        gemini_tool_state_upserted = _persist_gemini_tool_calls_state(
            tool_calls=tool_calls_out,
            model_name=use_model,
            trace_id=trace_id,
            db_path=proxy_db_path,
        )
        content_parts = _assistant_text_parts_from_ollama_message(oll_msg)
        content_out = openai_msg.get("content")
        content_str = content_out if isinstance(content_out, str) else ("" if content_out is None else str(content_out))
        budget_error = _output_budget_exhaustion_error(trace, data if isinstance(data, dict) else None)
        if budget_error and not tool_calls_out:
            content_str = f"{content_str}\n\n{budget_error}".strip() if content_str.strip() else budget_error
            content_parts = {
                "visible_content": content_str,
                "reasoning_content": content_parts["reasoning_content"],
                "final_content": f"{content_parts['final_content']}\n\n{budget_error}".strip(),
            }
            finish = "length"

        latency_ms = int((time.time() - start_time) * 1000)
        _pt = max(1, int(len(json.dumps(native_ollama_messages_for_upstream, ensure_ascii=False)) / 4))
        _ct = max(1, int(len(content_str or "") / 4))
        w.set_latest_request_total_tokens(_pt + _ct)

        _metric_model = "redacted" if private_build else use_model
        increment("rag_requests_total", tags={"model": _metric_model, "is_autocomplete": str(is_autocomplete)})
        histogram("rag_latency_ms", latency_ms, tags={"model": _metric_model})
        histogram("rag_prompt_tokens", _pt, tags={"model": _metric_model})
        histogram("rag_completion_tokens", _ct, tags={"model": _metric_model})
        if rag_ctx:
            gauge("rag_chunks_count", len(rag_ctx.chunks_info), tags={"model": _metric_model})
            gauge("rag_max_score", rag_ctx.max_score, tags={"model": _metric_model})
            if rag_ctx.max_score < 0.5:
                increment("rag_low_confidence", tags={"model": _metric_model})
        if not rag_ctx or not rag_ctx.chunks_info:
            increment("rag_empty_results", tags={"model": _metric_model})

        if not private_build:
            _RAG_LOG.debug(
                json.dumps(
                    _rag_request_completed_payload(
                        user_query=user_query,
                        trace_id=trace_id,
                        use_model=use_model,
                        requested_model=requested_model,
                        latency_ms=latency_ms,
                        prompt_tokens=_pt,
                        completion_tokens=_ct,
                        rag_context_for_obs=rag_ctx_for_log,
                        rag_timings=rag_timings,
                        trace=trace,
                        stream=bool(stream),
                        is_autocomplete=bool(is_autocomplete),
                        native_tools=True,
                    )
                )
            )
        trace["response"] = {
            "latency_ms": latency_ms,
            "tool_calls_count": len(tool_calls_out),
            "native_tools": True,
            **_trace_ollama_api_metrics(data if isinstance(data, dict) else None, model_id=use_model),
        }
        _apply_trace_response_text_fields(
            trace["response"],
            visible_content=content_parts["visible_content"] or content_str,
            reasoning_content=content_parts["reasoning_content"],
            final_content=content_parts["final_content"],
            log_preview=log_preview,
        )
        _apply_response_diagnostics(trace)
        if tool_calls_out:
            trace["response"]["tool_calls"] = tool_calls_out
        if gemini_tool_state_upserted:
            trace["response"]["gemini_tool_state_upserted_count"] = int(gemini_tool_state_upserted)
        if shell_sanitize_count:
            trace["response"]["shell_tool_sanitized_count"] = int(shell_sanitize_count)

        choice_msg: dict[str, object] = {
            "role": "assistant",
            "content": None if tool_calls_out else (content_str or None),
        }
        if tool_calls_out:
            choice_msg["tool_calls"] = tool_calls_out
        response_data: dict[str, object] = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": 0,
            "model": client_visible_model,
            "choices": [
                {
                    "index": 0,
                    "message": choice_msg,
                    "finish_reason": finish,
                }
            ],
        }
        if include_rag_metadata and rag_ctx:
            _rm: dict[str, object] = {
                "chunks_info": rag_ctx.chunks_info,
                "max_score": rag_ctx.max_score,
                "chunks_count": len(rag_ctx.chunks_info),
            }
            _rt = getattr(rag_ctx, "rag_trace", None)
            if isinstance(_rt, list):
                _rm["rag_trace"] = _rt
            _cr = getattr(rag_ctx, "coverage_report", None)
            if isinstance(_cr, dict):
                _rm["coverage_report"] = _cr
            _rq = getattr(rag_ctx, "rag_quality", None)
            if isinstance(_rq, dict):
                _rm["rag_quality"] = _rq
            response_data["rag_metadata"] = _rm

        if not stream:
            trace["steps"].append(
                {
                    "name": "provider_chat_native_tools",
                    "duration_ms": int(latency_ms),
                    "tokens_in_est": _pt,
                    "tokens_out_est": _ct,
                }
            )
            publish_response_artifacts(
                visible_content=content_parts["visible_content"] or content_str,
                reasoning_content=content_parts["reasoning_content"],
                final_content=content_parts["final_content"],
            )
            publish_trace(trace)
            if not private_build:
                persist_proxy_request_log(
                    message=f"Proxy request (native tools): {user_query[:100]}...",
                    response_preview=(content_str or ""),
                    latency_ms_value=latency_ms,
                    trace_payload=trace,
                    stream_value=False,
                    include_rag_fields=False,
                    include_token_fields=False,
                    warn_label="native-tools",
                )
            return jsonify(response_data)

        trace["request"]["sse_single_chunk"] = True

        def generate_sse_native_single() -> Iterator[str]:
            oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
            yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
            if content_str:
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': content_str}, 'finish_reason': None}]})}\n\n"
            if tool_calls_out:
                payload_calls = _sse_tool_calls_payload(tool_calls_out)
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'tool_calls': payload_calls}, 'finish_reason': None}]})}\n\n"
            yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]})}\n\n"
            yield "data: [DONE]\n\n"

            trace["ollama"]["chat_stream"] = False
            trace["steps"].append(
                {
                    "name": "provider_chat_native_tools_sse_single",
                    "duration_ms": int(latency_ms),
                    "tokens_in_est": _pt,
                    "tokens_out_est": _ct,
                }
            )
            publish_response_artifacts(
                visible_content=content_parts["visible_content"] or content_str,
                reasoning_content=content_parts["reasoning_content"],
                final_content=content_parts["final_content"],
            )
            publish_trace(trace)
            if not private_build:
                persist_proxy_request_log(
                    message=f"Proxy request (native tools SSE single): {user_query[:100]}...",
                    response_preview=(content_str or ""),
                    latency_ms_value=latency_ms,
                    trace_payload=trace,
                    stream_value=True,
                    include_rag_fields=False,
                    include_token_fields=False,
                    ollama_chat_stream=False,
                    sse_single_chunk=True,
                    warn_label="native-tools SSE single",
                )
            w.set_proxy_status(w.status_idle)
            w.set_latest_request_seconds(time.time() - start_time)
            w.set_latest_request_total_tokens(_pt + _ct)

        return Response(
            generate_sse_native_single(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if tools and tool_choice_effective != "none":
        if not post_tool_success_turn:
            tool_json_instruction = _build_tool_json_instruction(
                selected_edit_tool_name, selected_edit_tool
            )
            if tool_json_instruction:
                ollama_messages.append({"role": "system", "content": tool_json_instruction})
            excerpt_sys = _workspace_selection_snippet(user_query or last_user or "").strip()
            if not excerpt_sys:
                excerpt_sys = (
                    _client_selection_snippet(user_query or last_user or "").strip()
                    or _client_files_snippet(user_query or last_user or "").strip()
                )
            if excerpt_sys:
                ollama_messages.append({"role": "system", "content": excerpt_sys})

        if input_budget is not None:
            try:
                _upstream_cap_raw = os.getenv(
                    "LLM_PROXY_UPSTREAM_MESSAGES_JSON_CAP", "380000"
                ).strip()
                _upstream_json_cap = int(_upstream_cap_raw)
            except (TypeError, ValueError):
                _upstream_json_cap = 380_000
            _upstream_json_cap = max(160_000, min(_upstream_json_cap, 2_000_000))
            _budget_json_cap = min(
                _upstream_json_cap,
                int(input_budget.get("input_budget_json_chars") or _upstream_json_cap),
            )
            ollama_messages, compact_diag = _compact_upstream_messages_for_budget(
                ollama_messages,
                budget_json_chars=_budget_json_cap,
            )
            compact_diag["reserved_output_tokens"] = input_budget["reserved_output_tokens"]
            compact_diag["safety_margin_tokens"] = input_budget["safety_margin_tokens"]
            compact_diag["input_budget_tokens"] = input_budget["input_budget_tokens"]
            if compact_diag.get("compacted") or compact_diag.get("still_over_budget_after_history_compaction"):
                trace["request"]["upstream_context_compaction"] = compact_diag

        trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(ollama_messages)
        trace["ollama"]["model"] = use_model
        publish_trace(trace)

    stream_tool_mode = bool(
        stream and tools and tool_choice_effective != "none" and not post_tool_success_turn
    )
    if stream_tool_mode:
        w.set_proxy_status(w.status_response)
        stream_start_time = time.time()
        stream_tool_error: str | None = None
        try:
            streamed_content = chat_client.chat(
                ollama_messages,
                use_model,
                stream=False,
                options=ollama_options_overlay(),
                think=ollama_think,
            )
        except Exception:
            # Retry once with compact context; large prompts can trigger Ollama 500 on some models.
            compact_messages: list[dict[str, object]] = []
            if ollama_messages:
                first_system = next((m for m in ollama_messages if isinstance(m, dict) and m.get("role") == "system"), None)
                last_user_msg = next((m for m in reversed(ollama_messages) if isinstance(m, dict) and m.get("role") == "user"), None)
                if isinstance(first_system, dict):
                    compact_messages.append(first_system)
                if isinstance(last_user_msg, dict):
                    compact_messages.append(last_user_msg)
            try:
                streamed_content = chat_client.chat(
                    compact_messages or ollama_messages,
                    use_model,
                    stream=False,
                    options=ollama_options_overlay(),
                    think=ollama_think,
                )
            except Exception as e2:
                if not private_build:
                    w.log_webui_error("rag_routes.chat_completions", e2, {"stage": "chat_stream_tool_mode"})
                _log_rag_error_private("chat_stream_tool_mode", e2, private_build=private_build)
                stream_tool_error = str(e2)
                streamed_content = ""
        finally:
            w.set_proxy_status(w.status_idle)
            w.set_latest_request_seconds(time.time() - start_time)

        if stream_tool_error:
            # Do not fail the whole request: fallback to plain streaming branch below.
            trace["response"]["tool_mode_error"] = stream_tool_error[:500]
            publish_trace(trace)
        edit_payload = _extract_edit_from_response(streamed_content or "")
        tool_plain_fallback = (streamed_content or "").strip()

        if (not stream_tool_error) and edit_payload and selected_edit_tool_name:
            tool_args = _build_tool_arguments(
                selected_tool_name=selected_edit_tool_name,
                selected_tool=selected_edit_tool,
                edit_payload=edit_payload,
                user_query=user_query,
            )
            if not selected_tool_write_capable:
                # Client tool exists but cannot carry edit text; don't attempt server-side terminal writes.
                tool_plain_fallback = (
                    f"Cannot apply edit: client tool `{selected_edit_tool_name}` schema does not accept file content. "
                    "Enable a write-capable file edit tool in the IDE (e.g., edit_file/save_file/replace_in_file_range with content/new_text/replacement)."
                )
                edit_payload = None
            elif not _tool_args_have_substantive_body(selected_edit_tool_name, tool_args):
                # Model produced an edit payload without actual content.
                tool_plain_fallback = (
                    "Cannot apply edit: model did not provide a non-empty edit body (content/new_text/replacement). "
                    "Please retry."
                )
                edit_payload = None
            else:
                tool_call = {
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {
                        "name": selected_edit_tool_name,
                        "arguments": json.dumps(tool_args, ensure_ascii=False),
                    },
                }
                trace["response"] = {
                    "content_preview": "",
                    "content_length_chars": 0,
                    "latency_ms": int((time.time() - stream_start_time) * 1000),
                    "tool_calls_count": 1,
                    "tool_calls": [tool_call],
                }
                publish_trace(trace)

                _stm_lat = int((time.time() - stream_start_time) * 1000)
                if not private_build:
                    persist_proxy_request_log(
                        message=f"Proxy request (stream tool): {user_query[:100]}...",
                        response_preview="",
                        latency_ms_value=_stm_lat,
                        trace_payload=trace,
                        stream_value=True,
                        include_rag_fields=True,
                        include_token_fields=True,
                        prompt_tokens_value=0,
                        completion_tokens_value=0,
                        total_tokens_value=0,
                        extra_metadata={"stream_tool_mode": "tool_calls"},
                        warn_label="stream_tool_mode (tool_calls)",
                    )

                    _RAG_LOG.debug(
                        json.dumps(
                            _rag_request_completed_payload(
                                user_query=user_query,
                                trace_id=trace_id,
                                use_model=use_model,
                                requested_model=requested_model,
                                latency_ms=_stm_lat,
                                prompt_tokens=0,
                                completion_tokens=0,
                                rag_context_for_obs=rag_ctx_for_log,
                                rag_timings=rag_timings,
                                trace=trace,
                                stream=True,
                                is_autocomplete=bool(is_autocomplete),
                                native_tools=False,
                            )
                            | {"stream_tool_mode": "tool_calls"}
                        )
                    )

                def generate_sse_tool_call():
                    oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'id': tool_call['id'], 'type': 'function', 'function': {'name': selected_edit_tool_name, 'arguments': tool_call['function']['arguments']}}]}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]})}\n\n"
                    yield "data: [DONE]\n\n"

                return Response(
                    generate_sse_tool_call(),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
        if (not stream_tool_error) and (not edit_payload) and (not tool_plain_fallback):
            tool_plain_fallback = (
                "Model returned an empty response; no tool call was emitted. Please retry."
            )
        if (not stream_tool_error) and tool_plain_fallback:
            # If tool JSON was not produced, do not drop content: return plain assistant text via SSE.
            trace["response"] = {
                "latency_ms": int((time.time() - stream_start_time) * 1000),
                "tool_calls_count": 0,
            }
            _apply_trace_response_text_fields(
                trace["response"],
                visible_content=tool_plain_fallback,
                reasoning_content="",
                final_content=tool_plain_fallback,
                log_preview=log_preview,
            )
            _apply_response_diagnostics(trace)
            publish_response_artifacts(
                visible_content=tool_plain_fallback,
                reasoning_content="",
                final_content=tool_plain_fallback,
            )
            publish_trace(trace)

            _stm_lat_pt = int((time.time() - stream_start_time) * 1000)

            def _approx_tokens_stm(text: str) -> int:
                if not text:
                    return 0
                return max(1, int(len(text) / 4))

            _pt_stm = _approx_tokens_stm(
                " ".join(
                    _ollama_message_content_str(m.get("content"))
                    for m in ollama_messages
                    if isinstance(m, dict)
                )
            )
            _ct_stm = _approx_tokens_stm(tool_plain_fallback)
            _tt_stm = _pt_stm + _ct_stm
            if not private_build:
                persist_proxy_request_log(
                    message=f"Proxy request (stream tool plain): {user_query[:100]}...",
                    response_preview=tool_plain_fallback,
                    latency_ms_value=_stm_lat_pt,
                    trace_payload=trace,
                    stream_value=True,
                    include_rag_fields=True,
                    include_token_fields=True,
                    prompt_tokens_value=_pt_stm,
                    completion_tokens_value=_ct_stm,
                    total_tokens_value=_tt_stm,
                    extra_metadata={"stream_tool_mode": "plain_text_fallback"},
                    warn_label="stream_tool_mode (plain)",
                )

                _RAG_LOG.debug(
                    json.dumps(
                        _rag_request_completed_payload(
                            user_query=user_query,
                            trace_id=trace_id,
                            use_model=use_model,
                            requested_model=requested_model,
                            latency_ms=_stm_lat_pt,
                            prompt_tokens=_pt_stm,
                            completion_tokens=_ct_stm,
                            rag_context_for_obs=rag_ctx_for_log,
                            rag_timings=rag_timings,
                            trace=trace,
                            stream=True,
                            is_autocomplete=bool(is_autocomplete),
                            native_tools=False,
                        )
                        | {"stream_tool_mode": "plain_text_fallback"}
                    )
                )

            def generate_sse_plain_text():
                oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': tool_plain_fallback}, 'finish_reason': None}]})}\n\n"
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"

            return Response(
                generate_sse_plain_text(),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    if stream and build_sse_streaming:
        w.set_proxy_status(w.status_response)

        def generate_sse():
            oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
            stream_start_time = time.time()
            visible_content_parts: list[str] = []
            reasoning_content_parts: list[str] = []
            final_content_parts: list[str] = []
            ollama_done_reason: str | None = None
            ollama_done_payload: dict[str, Any] | None = None
            total_tokens_holder = [0]

            yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

            try:
                for kind, data in _iter_proxy_ollama_chat_stream(
                    chat_client, ollama_messages, use_model, ollama_think,
                    options_overlay=ollama_options_overlay(),
                ):
                    if kind in ("thinking_delta", "content_delta") and data:
                        text_part = str(data)
                        visible_content_parts.append(text_part)
                        if kind == "thinking_delta":
                            reasoning_content_parts.append(text_part)
                        else:
                            final_content_parts.append(text_part)
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': data}, 'finish_reason': None}]})}\n\n"
                    elif kind == "done" and isinstance(data, dict):
                        ollama_done_payload = data
                        ollama_done_reason = data.get("done_reason")
                    elif kind == "error":
                        err_text = f"[Error: {data}]"
                        visible_content_parts.append(err_text)
                        final_content_parts.append(err_text)
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': err_text}, 'finish_reason': None}]})}\n\n"
                        break
            except Exception as e:
                if not private_build:
                    w.log_webui_error("rag_routes.chat_completions", e, {"stage": "stream_chat"})
                _log_rag_error_private("stream_chat", e, private_build=private_build)
                err_text = f"[Error: {e}]"
                visible_content_parts.append(err_text)
                final_content_parts.append(err_text)
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': err_text}, 'finish_reason': None}]})}\n\n"

            full_response = "".join(visible_content_parts)
            reasoning_content = "".join(reasoning_content_parts)
            final_content = "".join(final_content_parts)
            budget_error = _output_budget_exhaustion_error(trace, ollama_done_payload)
            if budget_error:
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': budget_error}, 'finish_reason': None}]})}\n\n"
                full_response = f"{full_response}\n\n{budget_error}".strip() if full_response.strip() else budget_error
                final_content = f"{final_content}\n\n{budget_error}".strip() if final_content.strip() else budget_error

            if not full_response.strip():
                fallback = "Model returned an empty response. Please retry."
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': fallback}, 'finish_reason': None}]})}\n\n"
                full_response = fallback
                final_content = fallback

            finish_reason = openai_finish_reason_from_ollama(
                {}, ollama_done_reason=ollama_done_reason,
            )
            if budget_error:
                finish_reason = "length"
            yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}]})}\n\n"
            yield "data: [DONE]\n\n"

            stream_latency_ms = int((time.time() - stream_start_time) * 1000)

            def _approx_tokens(text: str) -> int:
                if not text:
                    return 0
                return max(1, int(len(text) / 4))

            prompt_text = " ".join(
                _ollama_message_content_str(m.get("content"))
                for m in ollama_messages
                if isinstance(m, dict)
            )
            prompt_tokens_approx = _approx_tokens(prompt_text)
            completion_tokens_approx = _approx_tokens(full_response)
            total_tokens_approx = prompt_tokens_approx + completion_tokens_approx
            total_tokens_holder[0] = total_tokens_approx

            trace["ollama"]["chat_stream"] = True
            trace["ollama"]["tokens_estimates"] = {
                "prompt_tokens_estimated": prompt_tokens_approx,
                "completion_tokens_estimated": completion_tokens_approx,
                "total_tokens_estimated": total_tokens_approx,
            }
            trace["response"] = {
                "latency_ms": stream_latency_ms,
                **_trace_ollama_api_metrics(ollama_done_payload),
            }
            _apply_trace_response_text_fields(
                trace["response"],
                visible_content=full_response,
                reasoning_content=reasoning_content,
                final_content=final_content,
                log_preview=log_preview,
            )
            _apply_response_diagnostics(trace)
            trace["steps"].append({
                "name": "provider_chat_stream",
                "duration_ms": stream_latency_ms,
                "tokens_in_est": prompt_tokens_approx,
                "tokens_out_est": completion_tokens_approx,
            })
            publish_response_artifacts(
                visible_content=full_response,
                reasoning_content=reasoning_content,
                final_content=final_content,
            )
            publish_trace(trace)

            if not private_build:
                persist_proxy_request_log(
                    message=f"Proxy request (stream): {user_query[:100]}...",
                    response_preview=full_response,
                    latency_ms_value=stream_latency_ms,
                    trace_payload=trace,
                    stream_value=True,
                    include_rag_fields=True,
                    include_token_fields=True,
                    prompt_tokens_value=prompt_tokens_approx,
                    completion_tokens_value=completion_tokens_approx,
                    total_tokens_value=total_tokens_approx,
                    ollama_chat_stream=True,
                    warn_label="stream",
                )

                _RAG_LOG.debug(
                    json.dumps(
                        _rag_request_completed_payload(
                            user_query=user_query,
                            trace_id=trace_id,
                            use_model=use_model,
                            requested_model=requested_model,
                            latency_ms=stream_latency_ms,
                            prompt_tokens=prompt_tokens_approx,
                            completion_tokens=completion_tokens_approx,
                            rag_context_for_obs=rag_ctx_for_log,
                            rag_timings=rag_timings,
                            trace=trace,
                            stream=True,
                            is_autocomplete=bool(is_autocomplete),
                            native_tools=False,
                        )
                    )
                )
                _RAG_LOG.debug(
                    "RAG response (stream) model=%s len=%s preview=%s",
                    use_model,
                    len(full_response),
                    full_response[:log_preview] if full_response else "",
                )

            w.set_proxy_status(w.status_idle)
            w.set_latest_request_seconds(time.time() - start_time)
            w.set_latest_request_total_tokens(total_tokens_holder[0] or None)

        return Response(
            generate_sse(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    budget_error = ""
    try:
        w.set_proxy_status(w.status_response)
        content_parts = _proxy_ollama_chat_text_parts(
            chat_client,
            ollama_messages,
            use_model,
            ollama_think,
            options_overlay=ollama_options_overlay(),
        )
        content = content_parts["visible_content"]
        if _degenerate_assistant_reply(content):
            content = _PLACEHOLDER_REPLY_FALLBACK_EN
            content_parts = {
                "visible_content": content,
                "reasoning_content": "",
                "final_content": content,
                "ollama_payload": content_parts.get("ollama_payload") if isinstance(content_parts, dict) else {},
            }
        budget_error = _output_budget_exhaustion_error(
            trace,
            content_parts.get("ollama_payload") if isinstance(content_parts, dict) else None,
        )
        if budget_error:
            content = f"{content}\n\n{budget_error}".strip() if str(content or "").strip() else budget_error
            content_parts = {
                "visible_content": content,
                "reasoning_content": str(content_parts.get("reasoning_content") or ""),
                "final_content": f"{content_parts.get('final_content') or ''}\n\n{budget_error}".strip(),
                "ollama_payload": content_parts.get("ollama_payload") if isinstance(content_parts, dict) else {},
            }
    except Exception as e:
        if not private_build:
            w.log_webui_error("rag_routes.chat_completions", e, {"stage": "chat"})
        _log_rag_error_private("chat", e, private_build=private_build)
        return jsonify({"error": str(e)}), 500
    finally:
        w.set_proxy_status(w.status_idle)
        w.set_latest_request_seconds(time.time() - start_time)
    latency_ms = int((time.time() - start_time) * 1000)
    _prompt_text = " ".join(
        _ollama_message_content_str(m.get("content"))
        for m in ollama_messages
        if isinstance(m, dict)
    )
    prompt_tokens_approx = max(1, int(len(_prompt_text) / 4))
    completion_tokens_approx = max(1, int(len(content or "") / 4))
    _total_tokens_approx = prompt_tokens_approx + completion_tokens_approx
    w.set_latest_request_total_tokens(_total_tokens_approx)
    
    # Record metrics for observability (non-streaming path)
    _metric_model_ns = "redacted" if private_build else use_model
    increment("rag_requests_total", tags={"model": _metric_model_ns, "is_autocomplete": str(is_autocomplete)})
    histogram("rag_latency_ms", latency_ms, tags={"model": _metric_model_ns})
    histogram("rag_prompt_tokens", prompt_tokens_approx, tags={"model": _metric_model_ns})
    histogram("rag_completion_tokens", completion_tokens_approx, tags={"model": _metric_model_ns})
    if rag_ctx:
        gauge("rag_chunks_count", len(rag_ctx.chunks_info), tags={"model": _metric_model_ns})
        gauge("rag_max_score", rag_ctx.max_score, tags={"model": _metric_model_ns})
        if rag_ctx.max_score < 0.5:
            increment("rag_low_confidence", tags={"model": _metric_model_ns})
    if not rag_ctx or not rag_ctx.chunks_info:
        increment("rag_empty_results", tags={"model": _metric_model_ns})

    if not private_build:
        _RAG_LOG.debug(
            json.dumps(
                _rag_request_completed_payload(
                    user_query=user_query,
                    trace_id=trace_id,
                    use_model=use_model,
                    requested_model=requested_model,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens_approx,
                    completion_tokens=completion_tokens_approx,
                    rag_context_for_obs=rag_ctx_for_log,
                    rag_timings=rag_timings,
                    trace=trace,
                    stream=bool(stream),
                    is_autocomplete=bool(is_autocomplete),
                    native_tools=False,
                )
            )
        )

    content_len = len(content or "")
    content_preview = _text_preview(content or "", log_preview)
    if not private_build:
        _RAG_LOG.debug(
            "RAG response model=%s len=%s preview=%s",
            use_model,
            content_len,
            content_preview,
        )
    trace["ollama"]["tokens_estimates"] = {
        "prompt_tokens_estimated": prompt_tokens_approx,
        "completion_tokens_estimated": completion_tokens_approx,
        "total_tokens_estimated": _total_tokens_approx,
    }
    trace["response"] = {
        "latency_ms": latency_ms,
        **_trace_ollama_api_metrics(
            content_parts.get("ollama_payload") if isinstance(content_parts, dict) else None,
            model_id=use_model,
        ),
    }
    _apply_trace_response_text_fields(
        trace["response"],
        visible_content=content_parts["visible_content"],
        reasoning_content=content_parts["reasoning_content"],
        final_content=content_parts["final_content"],
        log_preview=log_preview,
    )
    _apply_response_diagnostics(trace)
    trace["steps"].append(
        {
            "name": "ollama_chat",
            "duration_ms": int(latency_ms),
            "tokens_in_est": prompt_tokens_approx,
            "tokens_out_est": completion_tokens_approx,
        }
    )
    publish_response_artifacts(
        visible_content=content_parts["visible_content"],
        reasoning_content=content_parts["reasoning_content"],
        final_content=content_parts["final_content"],
    )
    publish_trace(trace)
    tool_calls: list[dict[str, object]] = []
    if (
        tools
        and tool_choice_effective != "none"
        and not post_tool_success_turn
        and (not stream or not build_sse_streaming)
    ):
        edit_payload = _extract_edit_from_response(content or "")
        if edit_payload and selected_edit_tool_name:
            tool_args = _build_tool_arguments(
                selected_tool_name=selected_edit_tool_name,
                selected_tool=selected_edit_tool,
                edit_payload=edit_payload,
                user_query=user_query,
            )
            if selected_tool_write_capable and _tool_args_have_substantive_body(selected_edit_tool_name, tool_args):
                tool_calls = [
                    {
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": selected_edit_tool_name,
                            "arguments": json.dumps(tool_args, ensure_ascii=False),
                        },
                    }
                ]
            elif not selected_tool_write_capable:
                content = (
                    f"Cannot apply edit: client tool `{selected_edit_tool_name}` schema does not accept file content. "
                    "Enable a write-capable file edit tool in the IDE (e.g., edit_file/save_file/replace_in_file_range with content/new_text/replacement)."
                )

    trace["response"]["tool_calls_count"] = len(tool_calls)
    if tool_calls:
        trace["response"]["tool_calls"] = tool_calls
        publish_trace(trace)

    _msg_obj: dict[str, object] = {
        "role": "assistant",
        "content": None if tool_calls else content,
    }
    if tool_calls:
        _msg_obj["tool_calls"] = tool_calls
    choice = {
        "index": 0,
        "message": _msg_obj,
        "finish_reason": "tool_calls" if tool_calls else ("length" if budget_error else "stop"),
    }
    response_data = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": 0,
        "model": client_visible_model,
        "choices": [choice],
    }
    
    # Add RAG metadata if requested
    if include_rag_metadata and rag_ctx:
        _rm2: dict[str, object] = {
            "chunks_info": rag_ctx.chunks_info,
            "max_score": rag_ctx.max_score,
            "chunks_count": len(rag_ctx.chunks_info),
        }
        _rt2 = getattr(rag_ctx, "rag_trace", None)
        if isinstance(_rt2, list):
            _rm2["rag_trace"] = _rt2
        _cr2 = getattr(rag_ctx, "coverage_report", None)
        if isinstance(_cr2, dict):
            _rm2["coverage_report"] = _cr2
        _rq2 = getattr(rag_ctx, "rag_quality", None)
        if isinstance(_rq2, dict):
            _rm2["rag_quality"] = _rq2
        response_data["rag_metadata"] = _rm2

    if stream:
        trace["request"]["sse_single_chunk"] = True
        trace["ollama"]["chat_stream"] = False
        publish_trace(trace)

        finish_sse = str(choice.get("finish_reason") or ("tool_calls" if tool_calls else "stop"))
        rid = str(response_data.get("id") or f"chatcmpl-{uuid.uuid4().hex[:24]}")

        def generate_sse_plain_single() -> Iterator[str]:
            yield f"data: {json.dumps({'id': rid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
            if content:
                yield f"data: {json.dumps({'id': rid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]})}\n\n"
            if tool_calls:
                payload_tc = _sse_tool_calls_payload(tool_calls)
                yield f"data: {json.dumps({'id': rid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'tool_calls': payload_tc}, 'finish_reason': None}]})}\n\n"
            yield f"data: {json.dumps({'id': rid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_sse}]})}\n\n"
            yield "data: [DONE]\n\n"
            if not private_build:
                persist_proxy_request_log(
                    message=f"Proxy request (SSE single): {user_query[:100]}...",
                    response_preview=content_preview,
                    latency_ms_value=latency_ms,
                    trace_payload=trace,
                    stream_value=True,
                    include_rag_fields=True,
                    include_token_fields=True,
                    prompt_tokens_value=prompt_tokens_approx,
                    completion_tokens_value=completion_tokens_approx,
                    total_tokens_value=_total_tokens_approx,
                    ollama_chat_stream=False,
                    sse_single_chunk=True,
                    warn_label="SSE single",
                )

        return Response(
            generate_sse_plain_single(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Persist trace for non-stream requests
    if not private_build:
        persist_proxy_request_log(
            message=f"Proxy request: {user_query[:100]}...",
            response_preview=content_preview,
            latency_ms_value=latency_ms,
            trace_payload=trace,
            stream_value=False,
            include_rag_fields=True,
            include_token_fields=True,
            prompt_tokens_value=prompt_tokens_approx,
            completion_tokens_value=completion_tokens_approx,
            total_tokens_value=_total_tokens_approx,
            warn_label="non-stream",
        )

    return jsonify(response_data)
