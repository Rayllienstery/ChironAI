"""OpenAI /v1/chat/completions handler."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from collections.abc import Iterator
from typing import Any

try:
    from chironai_rag.consumers import RAG_COLLECTION_APP_SETTING
except ImportError:
    RAG_COLLECTION_APP_SETTING = "rag_collection"

from flask import Response, jsonify, request

from infrastructure.metrics import increment, histogram, gauge

from infrastructure.ollama.model_capabilities import (
    caps_supports_thinking,
    caps_supports_tools,
    chat_error_suggests_no_think,
    chat_error_suggests_no_tools,
    get_cached_ollama_capabilities,
)
from llm_proxy.contracts import LlmProxyWiring
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


def _log_rag_error(stage: str, error: Exception) -> None:
    _RAG_LOG.error("RAG stage=%s | %s: %s", stage, type(error).__name__, error)


def _log_rag_error_private(stage: str, error: Exception, *, private_build: bool) -> None:
    if private_build:
        _RAG_LOG.error("RAG stage=%s | %s", stage, type(error).__name__)
    else:
        _log_rag_error(stage, error)


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


def _trace_ollama_messages_for_ui(ollama_messages: list[Any]) -> list[dict[str, Any]]:
    """Snapshots messages for Proxy Trace (preview + full text for the WebUI modal)."""
    out: list[dict[str, Any]] = []
    for m in ollama_messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role") or ""
        _raw_content = m.get("content")
        if isinstance(_raw_content, str):
            content_str = _raw_content
        elif _raw_content is None:
            content_str = ""
        else:
            content_str = json.dumps(_raw_content, ensure_ascii=False)
        content_len = len(content_str)
        lim = _OLLAMA_TRACE_MSG_PREVIEW
        out.append(
            {
                "role": str(role),
                "content_length_chars": int(content_len),
                "content_preview": content_str[:lim] + ("..." if content_len > lim else ""),
                "content_full": content_str,
            }
        )
    return out


def _merge_ollama_visible_text(thinking: str | None, content: str | None) -> str:
    """Single assistant string for the client: thinking then content when both exist."""
    t = (thinking or "").strip()
    c = (content or "").strip()
    if t and c:
        return f"{t}\n\n{c}"
    return c or t


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
    """Ollama native ``think`` with Qwen3 often returns only placeholder output (e.g. ``.``)."""
    return "qwen3" in (model_name or "").lower()


def effective_ollama_think_from_body(
    body: dict[str, Any],
    ollama_model: str | None,
    *,
    capabilities: frozenset[str] | None = None,
) -> bool | str | None:
    """
    Value actually sent to Ollama ``/api/chat``.

    For Qwen3, omitting ``think`` often leaves the model's template with thinking enabled by default,
    which yields placeholder-only output. Always send explicit ``think: false`` for those models.
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


def _proxy_ollama_chat_text(
    chat_client: Any,
    messages: list[dict[str, Any]],
    model: str,
    think: bool | str | None,
    *,
    options_overlay: dict[str, Any] | None = None,
) -> str:
    """Non-stream /api/chat; returns merged visible assistant text (thinking + content)."""
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
        content = (msg.get("content") or "").strip() if isinstance(msg, dict) else ""
        th = msg.get("thinking") if isinstance(msg, dict) else None
        thinking_out = th.strip() if isinstance(th, str) else None
        return _merge_ollama_visible_text(thinking_out, content)
    text = chat_client.chat(
        messages, model, stream=False, options=options_overlay if options_overlay else None, think=think
    )
    return (text or "").strip()


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
    ``("content_delta", full_text)`` when the client has no streaming support.
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
    if tool_choice not in (None, "", "auto"):
        payload["tool_choice"] = tool_choice

    stream_fn = getattr(chat_client, "iter_chat_api_stream_events", None)
    if callable(stream_fn):
        yield from stream_fn(payload)
    else:
        chat_api_fn = getattr(chat_client, "chat_api", None)
        if callable(chat_api_fn):
            data = chat_api_fn(payload)
            msg = data.get("message") if isinstance(data.get("message"), dict) else {}
            content = (msg.get("content") or "").strip() if isinstance(msg, dict) else ""
            th_raw = msg.get("thinking") if isinstance(msg, dict) else None
            th = th_raw.strip() if isinstance(th_raw, str) else None
            visible = _merge_ollama_visible_text(th, content)
            if visible:
                yield ("content_delta", visible)
            tc = msg.get("tool_calls") if isinstance(msg, dict) else None
            if isinstance(tc, list) and tc:
                yield ("tool_calls", tc)
        else:
            text = _proxy_ollama_chat_text(
                chat_client, messages, model, think, options_overlay=options_overlay,
            )
            if text:
                yield ("content_delta", text)
        yield ("done", {})


def _normalize_request_messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    """
    OpenAI chat uses ``messages``; some clients POST legacy ``prompt`` / ``suffix`` instead.
    Map to a single user message without model-specific fill-in-the-middle tokens.
    """
    raw = body.get("messages")
    if isinstance(raw, list) and len(raw) > 0:
        return raw

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
    }
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
    w.set_proxy_status(w.status_rag_search)

    proxy_settings: dict[str, object] = {}
    proxy_model_setting = ""
    try:
        _settings_repo_early = w.get_settings_repository()
        proxy_model_setting = (_settings_repo_early.get_app_setting("proxy_model") or "").strip()
        _ps_json_early = _settings_repo_early.get_app_setting("proxy_settings")
        if _ps_json_early:
            _loaded = json.loads(_ps_json_early)
            if isinstance(_loaded, dict):
                proxy_settings = _loaded
    except Exception:
        pass
    if not proxy_model_setting and proxy_settings.get("model"):
        proxy_model_setting = str(proxy_settings.get("model") or "").strip()

    stream = body.get("stream", False)
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
    _legacy_worker_ids = frozenset({"ChironAI-Worker", "rag-ollama"})
    if requested_model in _legacy_worker_ids:
        w.set_proxy_status(w.status_idle)
        return jsonify(
            {
                "error": (
                    "Legacy RAG model ids are removed; use an LLM Proxy build id or a concrete Ollama model tag."
                ),
            }
        ), 400
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

    if active_build and str(active_build.get("backend") or "").strip().lower() == "claw":
        from application.llm_proxy_build_forward import forward_claw_build_chat

        w.set_proxy_status(w.status_idle)
        return forward_claw_build_chat(body, active_build)

    if active_build and str(active_build.get("backend") or "").strip().lower() == "dumb":
        proxy_settings = merge_build_into_proxy_settings(proxy_settings, active_build)
        _om_b = str(active_build.get("ollama_model") or "").strip()
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

    private_build = bool(dumb_build_pipeline and active_build and bool(active_build.get("private")))
    if private_build:
        w.set_current_trace(None)

    def publish_trace(tr: dict[str, Any]) -> None:
        if private_build:
            w.set_current_trace(None)
        else:
            w.set_current_trace(tr)

    autocomplete_id = rt.autocomplete_model_logical_id
    is_autocomplete = requested_model == autocomplete_id
    proxy_autocomplete_ollama: str | None = None
    tools = body.get("tools") if isinstance(body.get("tools"), list) else []
    tool_choice = body.get("tool_choice")
    tool_choice_effective = tool_choice if tool_choice not in (None, "") else "auto"
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

    fetch_web_knowledge_raw = body.get("fetch_web_knowledge")
    if fetch_web_knowledge_raw is None:
        fetch_web_knowledge = bool(proxy_settings.get("fetch_web_knowledge", False))
    else:
        fetch_web_knowledge = bool(fetch_web_knowledge_raw)
    if is_autocomplete:
        fetch_web_knowledge = False

    _get_rag_prompt = w.get_rag_prompt_prefix_suffix
    rag_prompt_file_exists = w.rag_prompt_file_exists

    proxy_prompt_name_required: str | None = None
    if system_prefix is None:
        _pn = str(proxy_settings.get("prompt_name") or "").strip()
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
                    "error": "Dumb build is missing ollama_model; edit the build in LLM Proxy (builds).",
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
    context_length = len(last_user.split())
    if system_prefix is not None:
        effective_prefix = prefix
        effective_suffix = suffix
    else:
        effective_prefix, effective_suffix = _get_rag_prompt(proxy_prompt_name_required)
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

    trace["request"] = {
        "requested_model": requested_model,
        "actual_model": actual_model,
        "proxy_pipeline": "passthrough_only",
        "stream": bool(stream),
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
        "reasoning_level": explicit_reasoning or reasoning_level,
        "reasoning_for_prompt": reasoning_for_prompt,
        "user_query_preview": (user_query or "")[:500],
        "is_autocomplete": bool(is_autocomplete),
    }

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
    request_collection = (body.get("collection_name") or "").strip() or None
    collection_source = "request"
    if not request_collection:
        try:
            settings_repo = w.get_settings_repository()
            request_collection = (settings_repo.get_app_setting(RAG_COLLECTION_APP_SETTING) or "").strip() or None
            collection_source = "app_settings.rag_collection"
            if not request_collection:
                proxy_settings_json = settings_repo.get_app_setting("proxy_settings")
                if proxy_settings_json:
                    proxy_settings = json.loads(proxy_settings_json)
                    request_collection = (proxy_settings.get("rag_collection") or "").strip() or None
                    if request_collection:
                        collection_source = "proxy_settings.rag_collection"
        except Exception:
            request_collection = None
            collection_source = "default"
    if request_collection and not is_autocomplete:
        req_params, req_deps = w.get_rag_answer_params(
            webui_dir=webui_dir,
            collection_name=request_collection,
            prompt_name=proxy_prompt_name_required if system_prefix is None else None,
        )
        effective_prefix = system_prefix if system_prefix is not None else req_params.system_prefix
        effective_suffix = system_suffix if system_suffix is not None else req_params.system_suffix
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

    # Proxy: do not read settings from DB; rerank is configurable via proxy_rerank_enabled.
    effective_rerank_client = (
        effective_base_rerank_client if w.get_proxy_rerank_enabled() else None
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

        if not skip_rag_retrieval:
            use_merged = False
            if (
                fetch_web_knowledge
                and not request_collection
                and w.external_docs.available
                and w.external_docs.load_rag_sources_config
                and w.external_docs.resolve_rag_sources_for_request
                and w.external_docs.build_merged_rag_context
                and w.external_docs.qdrant_rag_search_adapter_cls is not None
            ):
                rag_sources_config = w.external_docs.load_rag_sources_config()
                body_rag_sources = body.get("rag_sources")
                if isinstance(body_rag_sources, list):
                    body_rag_sources = [str(x) for x in body_rag_sources]
                else:
                    body_rag_sources = None
                resolved = w.external_docs.resolve_rag_sources_for_request(last_user, messages, body_rag_sources, rag_sources_config)
                # Use merged path whenever we have any resolved source: enables generic discovery
                # (GitHub fetch for any framework name in the question) plus configured on-demand and RAG.
                if len(resolved) >= 1:
                    use_merged = True
                    # Trigger full crawl for resolved sources that are missing or stale when repo is on GitHub
                    try:
                        _settings_repo = w.get_settings_repository()
                        _ttl_days = w.get_framework_collection_ttl_days()
                        _ttl_raw = _settings_repo.get_app_setting("framework_collection_ttl_days")
                        if _ttl_raw is not None and str(_ttl_raw).strip() != "":
                            try:
                                _ttl_days = int(_ttl_raw)
                            except (TypeError, ValueError):
                                pass
                    except Exception:
                        _settings_repo = None
                        _ttl_days = 90
                    resolved_needs_refresh: list[tuple[str, str]] = []
                    if _settings_repo:
                        for cfg in resolved:
                            meta = None
                            try:
                                meta = _settings_repo.get_collection_meta(cfg.collection_name)
                            except Exception:
                                pass
                            if w.check_collection_freshness(meta, _ttl_days) != "fresh":
                                fid = (cfg.external_source_id or cfg.collection_name or "").strip().lower() or cfg.collection_name.lower()
                                resolved_needs_refresh.append((fid, cfg.collection_name))
                    work_list = list(needs_refresh)
                    for (fid, coll) in resolved_needs_refresh:
                        if coll not in [c for _, c in work_list]:
                            work_list.append((fid, coll))
                    if work_list and w.external_docs.load_github_repos and w.external_docs.ingest_github_repo_markdown and w.external_docs.http_fetch_client_cls and w.external_docs.qdrant_chunk_sink_cls and w.external_docs.get_latest_release_tag:
                        coll_to_framework_id = {}
                        for cfg in rag_sources_config:
                            fid = (cfg.external_source_id or cfg.collection_name or "").strip().lower()
                            if fid:
                                coll_to_framework_id[cfg.collection_name] = fid
                        github_repos_list = w.external_docs.load_github_repos()
                        by_framework_id = {(e.get("framework_id") or "").lower(): e for e in github_repos_list if e.get("framework_id")}

                        def _run_refresh(work: list) -> None:
                            try:
                                qdrant_url = w.get_qdrant_url()
                                fetch_client = w.external_docs.http_fetch_client_cls()
                                chunk_sink = w.external_docs.qdrant_chunk_sink_cls(base_url=qdrant_url)
                                repo = w.get_settings_repository()
                                def on_indexed(cname: str, fid: str, ver: str | None, last_at: str) -> None:
                                    repo.set_collection_meta(cname, fid, ver or "", last_at)
                                for _name, coll in work:
                                    fid = coll_to_framework_id.get(coll) or coll.lower()
                                    entry = by_framework_id.get(fid)
                                    if not entry:
                                        continue
                                    owner = entry.get("owner", "")
                                    repo_name = entry.get("repo", "")
                                    ref = entry.get("ref") or "main"
                                    if ref in ("latest", ""):
                                        tag = w.external_docs.get_latest_release_tag(f"{owner}/{repo_name}")
                                        if tag:
                                            ref = tag
                                        else:
                                            ref = "main"
                                    w.external_docs.ingest_github_repo_markdown(
                                        owner, repo_name, ref, coll, fid,
                                        fetch_client, chunk_sink, effective_embed_provider,
                                        max_depth=3,
                                        on_indexed=on_indexed,
                                    )
                                    break
                            except Exception as e:
                                _RAG_LOG.warning("Background framework refresh failed: %s", e)

                        background_refresh_started = True
                        trace["internet"]["background_refresh_started"] = True
                        threading.Thread(target=_run_refresh, args=(work_list,), daemon=True).start()

                    try:
                        qdrant_url = w.get_qdrant_url()
                    except Exception:
                        qdrant_url = "http://localhost:6333"
                    rag_search_adapter = w.external_docs.qdrant_rag_search_adapter_cls(base_url=qdrant_url)
                    fetch_client = w.external_docs.http_fetch_client_cls() if w.external_docs.http_fetch_client_cls is not None else None
                    external_sources_list = w.external_docs.load_external_sources() if w.external_docs.load_external_sources else []
                    merged_ctx, merged_timings = w.external_docs.build_merged_rag_context(
                        last_user,
                        resolved,
                        rag_search_adapter,
                        effective_embed_provider,
                        effective_context_chunk_chars,
                        effective_context_total_chars,
                        fetch_client=fetch_client,
                        external_sources=external_sources_list,
                        fresh_collection_names=project_fresh_collection_names,
                    )
                    rag_ctx_for_log = w.rag_context_factory(
                        context_text=merged_ctx.context_text,
                        chunks_info=merged_ctx.chunks_info,
                        max_score=merged_ctx.max_score,
                    )
                    rag_timings = merged_timings
            if not use_merged or rag_ctx_for_log is None:
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
        if rag_timings:
            w.set_latest_request_rag_steps(rag_timings)
            if not private_build:
                _RAG_LOG.info(
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
    _bf = getattr(w, "build_web_supplement_for_proxy", None)
    if callable(_bf) and not is_autocomplete:
        if doc_refactor_skip:
            web_sup_meta = {
                **web_sup_meta,
                "skip_reason": "workspace_doc_refactor",
                "duration_ms": 0,
            }
        else:
            try:
                _tws = time.time()
                _mx = float(rag_ctx_for_log.max_score) if rag_ctx_for_log is not None else 0.0
                ps: dict[str, Any] = {str(k): v for k, v in (proxy_settings or {}).items()}
                web_supplement_text, web_sup_meta = _bf(
                    last_user or "",
                    _mx,
                    float(effective_confidence_threshold),
                    ps,
                )
                web_sup_meta = {
                    **web_sup_meta,
                    "duration_ms": int((time.time() - _tws) * 1000),
                }
            except Exception as _wse:
                web_sup_meta = {**web_sup_meta, "error": str(_wse)}
                web_supplement_text = None
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
            arguments_to_openai_string,
            ollama_message_to_openai_assistant,
            ollama_tools_from_openai,
            openai_finish_reason_from_ollama,
        )

        trace["request"]["native_tools"] = True
        oll_tools = ollama_tools_from_openai([t for t in tools if isinstance(t, dict)])

        # ------------------------------------------------------------------ #
        #  STREAMING native tools: true token-by-token SSE                    #
        # ------------------------------------------------------------------ #
        if stream:
            w.set_proxy_status(w.status_response)

            def generate_sse_native():
                oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                stream_start_time = time.time()
                accumulated_content: list[str] = []
                tool_calls_raw: list[dict[str, Any]] = []
                total_tokens_holder = [0]

                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

                try:
                    for kind, data in _iter_proxy_ollama_chat_stream(
                        chat_client, ollama_messages, use_model, ollama_think,
                        options_overlay=build_extra_options if build_extra_options else None,
                        tools=oll_tools,
                        tool_choice=tool_choice_effective,
                    ):
                        if kind == "content_delta" and data:
                            accumulated_content.append(data)
                            yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': data}, 'finish_reason': None}]})}\n\n"
                        elif kind == "tool_calls" and data:
                            tool_calls_raw = data
                        elif kind == "error":
                            accumulated_content.append(f"[Error: {data}]")
                            yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': f'[Error: {data}]'}, 'finish_reason': None}]})}\n\n"
                            break
                except Exception as exc:
                    if not private_build:
                        w.log_webui_error("rag_routes.chat_completions", exc, {"stage": "native_tools_stream"})
                    _log_rag_error_private("native_tools_stream", exc, private_build=private_build)
                    err_text = f"[Error: {exc}]"
                    accumulated_content.append(err_text)
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': err_text}, 'finish_reason': None}]})}\n\n"

                full_content = "".join(accumulated_content)
                stream_latency_ms = int((time.time() - stream_start_time) * 1000)

                if tool_calls_raw:
                    fake_msg: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls_raw}
                    if full_content:
                        fake_msg["content"] = full_content
                    openai_mapped = ollama_message_to_openai_assistant(fake_msg)
                    mapped_calls = openai_mapped.get("tool_calls") or []
                    finish_reason = "tool_calls"
                    if mapped_calls:
                        payload_calls: list[dict[str, object]] = []
                        for i, tc in enumerate(mapped_calls):
                            if not isinstance(tc, dict):
                                continue
                            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                            payload_calls.append({
                                "index": i,
                                "id": tc.get("id"),
                                "type": "function",
                                "function": {
                                    "name": fn.get("name"),
                                    "arguments": fn.get("arguments"),
                                },
                            })
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'tool_calls': payload_calls}, 'finish_reason': None}]})}\n\n"
                else:
                    finish_reason = "stop"

                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}]})}\n\n"
                yield "data: [DONE]\n\n"

                _pt = max(1, int(len(json.dumps(ollama_messages, ensure_ascii=False)) / 4))
                _ct = max(1, int(len(full_content) / 4))
                total_tokens_holder[0] = _pt + _ct

                trace["ollama"]["chat_stream"] = True
                trace["response"] = {
                    "content_preview": full_content[:log_preview],
                    "content_length_chars": len(full_content),
                    "latency_ms": stream_latency_ms,
                    "tool_calls_count": len(tool_calls_raw),
                    "native_tools": True,
                }
                if tool_calls_raw:
                    trace["response"]["tool_calls_raw"] = tool_calls_raw
                trace["steps"].append({
                    "name": "ollama_chat_native_tools_stream",
                    "duration_ms": stream_latency_ms,
                    "tokens_in_est": _pt,
                    "tokens_out_est": _ct,
                })
                publish_trace(trace)

                if not private_build:
                    try:
                        session_manager = w.get_session_manager()
                        session_manager.get_or_create_session("proxy")
                        logs_repo = w.get_logs_repository()
                        logs_repo.add_log(
                            session_id="proxy",
                            level="INFO",
                            message=f"Proxy request (native tools stream): {user_query[:100]}...",
                            source="proxy",
                            metadata={
                                "user_query": user_query[:500],
                                "response_preview": full_content[:500],
                                "trace_id": trace_id,
                                "model": use_model,
                                "latency_ms": stream_latency_ms,
                                "prompt_tokens": _pt,
                                "completion_tokens": _ct,
                                "total_tokens": total_tokens_holder[0],
                                "rag_context": rag_context_data,
                                "rag_steps": rag_timings,
                                "trace": trace,
                                "stream": True,
                                "ollama_chat_stream": True,
                                "is_autocomplete": bool(is_autocomplete),
                                "requested_model": requested_model,
                                "proxy_backend": proxy_backend_tag(),
                            },
                        )
                    except Exception as e:
                        _RAG_LOG.warning("Failed to log native-tools stream proxy request: %s", e)

                    _RAG_LOG.info(
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
        if build_extra_options:
            _co.update(build_extra_options)
        body_ollama: dict[str, object] = {
            "model": use_model,
            "messages": ollama_messages,
            "stream": False,
            "options": dict(_co),
        }
        if ollama_think is not None:
            body_ollama["think"] = ollama_think
        if oll_tools:
            body_ollama["tools"] = oll_tools
        if tool_choice_effective not in (None, "", "auto"):
            body_ollama["tool_choice"] = tool_choice_effective

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
                    ollama_messages,
                    use_model,
                    stream=False,
                    options=build_extra_options if build_extra_options else None,
                    think=ollama_think,
                )
                data = {"message": {"role": "assistant", "content": msg_only}}
        except Exception as e:
            if not private_build:
                w.log_webui_error("rag_routes.chat_completions", e, {"stage": "native_tools_ollama"})
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
        finish = openai_finish_reason_from_ollama(oll_msg)
        tool_calls_out = openai_msg.get("tool_calls") if isinstance(openai_msg.get("tool_calls"), list) else []
        content_out = openai_msg.get("content")
        content_str = content_out if isinstance(content_out, str) else ("" if content_out is None else str(content_out))

        latency_ms = int((time.time() - start_time) * 1000)
        _pt = max(1, int(len(json.dumps(ollama_messages, ensure_ascii=False)) / 4))
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
            _RAG_LOG.info(
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
                        stream=False,
                        is_autocomplete=bool(is_autocomplete),
                        native_tools=True,
                    )
                )
            )
        trace["response"] = {
            "content_preview": (content_str or "")[:log_preview],
            "content_length_chars": len(content_str or ""),
            "latency_ms": latency_ms,
            "tool_calls_count": len(tool_calls_out),
            "native_tools": True,
        }
        if tool_calls_out:
            trace["response"]["tool_calls"] = tool_calls_out
        trace["steps"].append(
            {
                "name": "ollama_chat_native_tools",
                "duration_ms": int(latency_ms),
                "tokens_in_est": _pt,
                "tokens_out_est": _ct,
            }
        )
        publish_trace(trace)

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
        if not private_build:
            try:
                session_manager = w.get_session_manager()
                session_manager.get_or_create_session("proxy")
                logs_repo = w.get_logs_repository()
                logs_repo.add_log(
                    session_id="proxy",
                    level="INFO",
                    message=f"Proxy request (native tools): {user_query[:100]}...",
                    source="proxy",
                    metadata={
                        "user_query": user_query[:500],
                        "response_preview": (content_str or "")[:500],
                        "trace_id": trace_id,
                        "model": use_model,
                        "latency_ms": latency_ms,
                        "trace": trace,
                        "stream": False,
                        "is_autocomplete": bool(is_autocomplete),
                        "requested_model": requested_model,
                        "proxy_backend": proxy_backend_tag(),
                    },
                )
            except Exception as e:
                _RAG_LOG.warning("Failed to log native-tools proxy request: %s", e)
        return jsonify(response_data)

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
                options=build_extra_options if build_extra_options else None,
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
                    options=build_extra_options if build_extra_options else None,
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
                    try:
                        session_manager = w.get_session_manager()
                        session_manager.get_or_create_session("proxy")
                        logs_repo = w.get_logs_repository()
                        logs_repo.add_log(
                            session_id="proxy",
                            level="INFO",
                            message=f"Proxy request (stream tool): {user_query[:100]}...",
                            source="proxy",
                            metadata={
                                "user_query": user_query[:500],
                                "response_preview": "",
                                "trace_id": trace_id,
                                "model": use_model,
                                "latency_ms": _stm_lat,
                                "prompt_tokens": 0,
                                "completion_tokens": 0,
                                "total_tokens": 0,
                                "rag_context": rag_context_data,
                                "rag_steps": rag_timings,
                                "trace": trace,
                                "stream": True,
                                "is_autocomplete": bool(is_autocomplete),
                                "requested_model": requested_model,
                                "proxy_backend": proxy_backend_tag(),
                                "stream_tool_mode": "tool_calls",
                            },
                        )
                    except Exception as e:
                        _RAG_LOG.warning("Failed to log proxy stream_tool_mode (tool_calls): %s", e)

                    _RAG_LOG.info(
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
                "content_preview": tool_plain_fallback[:log_preview],
                "content_length_chars": len(tool_plain_fallback),
                "latency_ms": int((time.time() - stream_start_time) * 1000),
                "tool_calls_count": 0,
            }
            publish_trace(trace)

            _stm_lat_pt = int((time.time() - stream_start_time) * 1000)

            def _approx_tokens_stm(text: str) -> int:
                if not text:
                    return 0
                return max(1, int(len(text) / 4))

            _pt_stm = _approx_tokens_stm(
                " ".join((m.get("content") or "") for m in ollama_messages if isinstance(m, dict))
            )
            _ct_stm = _approx_tokens_stm(tool_plain_fallback)
            _tt_stm = _pt_stm + _ct_stm
            if not private_build:
                try:
                    session_manager = w.get_session_manager()
                    session_manager.get_or_create_session("proxy")
                    logs_repo = w.get_logs_repository()
                    logs_repo.add_log(
                        session_id="proxy",
                        level="INFO",
                        message=f"Proxy request (stream tool plain): {user_query[:100]}...",
                        source="proxy",
                        metadata={
                            "user_query": user_query[:500],
                            "response_preview": tool_plain_fallback[:500],
                            "trace_id": trace_id,
                            "model": use_model,
                            "latency_ms": _stm_lat_pt,
                            "prompt_tokens": _pt_stm,
                            "completion_tokens": _ct_stm,
                            "total_tokens": _tt_stm,
                            "rag_context": rag_context_data,
                            "rag_steps": rag_timings,
                            "trace": trace,
                            "stream": True,
                            "is_autocomplete": bool(is_autocomplete),
                            "requested_model": requested_model,
                            "proxy_backend": proxy_backend_tag(),
                            "stream_tool_mode": "plain_text_fallback",
                        },
                    )
                except Exception as e:
                    _RAG_LOG.warning("Failed to log proxy stream_tool_mode (plain): %s", e)

                _RAG_LOG.info(
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

    if stream:
        w.set_proxy_status(w.status_response)

        def generate_sse():
            oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
            stream_start_time = time.time()
            accumulated_content: list[str] = []
            total_tokens_holder = [0]

            yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

            try:
                for kind, data in _iter_proxy_ollama_chat_stream(
                    chat_client, ollama_messages, use_model, ollama_think,
                    options_overlay=build_extra_options if build_extra_options else None,
                ):
                    if kind == "content_delta" and data:
                        accumulated_content.append(data)
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': data}, 'finish_reason': None}]})}\n\n"
                    elif kind == "error":
                        accumulated_content.append(f"[Error: {data}]")
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': f'[Error: {data}]'}, 'finish_reason': None}]})}\n\n"
                        break
            except Exception as e:
                if not private_build:
                    w.log_webui_error("rag_routes.chat_completions", e, {"stage": "stream_chat"})
                _log_rag_error_private("stream_chat", e, private_build=private_build)
                err_text = f"[Error: {e}]"
                accumulated_content.append(err_text)
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': err_text}, 'finish_reason': None}]})}\n\n"

            full_response = "".join(accumulated_content)

            if not full_response.strip():
                fallback = "Model returned an empty response. Please retry."
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {'content': fallback}, 'finish_reason': None}]})}\n\n"
                full_response = fallback

            yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': client_visible_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"

            stream_latency_ms = int((time.time() - stream_start_time) * 1000)

            def _approx_tokens(text: str) -> int:
                if not text:
                    return 0
                return max(1, int(len(text) / 4))

            prompt_text = " ".join(
                (m.get("content") or "") for m in ollama_messages if isinstance(m, dict)
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
                "content_preview": full_response[:log_preview]
                + ("..." if len(full_response) > log_preview else ""),
                "content_length_chars": len(full_response),
                "latency_ms": stream_latency_ms,
            }
            trace["steps"].append({
                "name": "ollama_chat_stream",
                "duration_ms": stream_latency_ms,
                "tokens_in_est": prompt_tokens_approx,
                "tokens_out_est": completion_tokens_approx,
            })
            publish_trace(trace)

            if not private_build:
                try:
                    session_manager = w.get_session_manager()
                    session_manager.get_or_create_session("proxy")
                    logs_repo = w.get_logs_repository()
                    logs_repo.add_log(
                        session_id="proxy",
                        level="INFO",
                        message=f"Proxy request (stream): {user_query[:100]}...",
                        source="proxy",
                        metadata={
                            "user_query": user_query[:500],
                            "response_preview": full_response[:500],
                            "trace_id": trace_id,
                            "model": use_model,
                            "latency_ms": stream_latency_ms,
                            "prompt_tokens": prompt_tokens_approx,
                            "completion_tokens": completion_tokens_approx,
                            "total_tokens": total_tokens_approx,
                            "rag_context": rag_context_data,
                            "rag_steps": rag_timings,
                            "trace": trace,
                            "stream": True,
                            "ollama_chat_stream": True,
                            "is_autocomplete": bool(is_autocomplete),
                            "requested_model": requested_model,
                            "proxy_backend": proxy_backend_tag(),
                        },
                    )
                except Exception as e:
                    _RAG_LOG.warning("Failed to log proxy stream request to database: %s", e)

                _RAG_LOG.info(
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
                _RAG_LOG.info(
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
    try:
        w.set_proxy_status(w.status_response)
        content = _proxy_ollama_chat_text(
            chat_client,
            ollama_messages,
            use_model,
            ollama_think,
            options_overlay=build_extra_options if build_extra_options else None,
        )
        if _degenerate_assistant_reply(content):
            content = _PLACEHOLDER_REPLY_FALLBACK_EN
    except Exception as e:
        if not private_build:
            w.log_webui_error("rag_routes.chat_completions", e, {"stage": "chat"})
        _log_rag_error_private("chat", e, private_build=private_build)
        return jsonify({"error": str(e)}), 500
    finally:
        w.set_proxy_status(w.status_idle)
        w.set_latest_request_seconds(time.time() - start_time)
    latency_ms = int((time.time() - start_time) * 1000)
    _prompt_text = " ".join((m.get("content") or "") for m in ollama_messages if isinstance(m, dict))
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
        _RAG_LOG.info(
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
                    stream=False,
                    is_autocomplete=bool(is_autocomplete),
                    native_tools=False,
                )
            )
        )

    content_len = len(content or "")
    content_preview = (content or "")[:log_preview]
    if content_len > log_preview:
        content_preview += "..."
    if not private_build:
        _RAG_LOG.info(
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
        "content_preview": content_preview,
        "content_length_chars": content_len,
        "latency_ms": latency_ms,
    }
    trace["steps"].append(
        {
            "name": "ollama_chat",
            "duration_ms": int(latency_ms),
            "tokens_in_est": prompt_tokens_approx,
            "tokens_out_est": completion_tokens_approx,
        }
    )
    publish_trace(trace)
    tool_calls: list[dict[str, object]] = []
    if (not stream) and tools and tool_choice_effective != "none" and not post_tool_success_turn:
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
        "finish_reason": "tool_calls" if tool_calls else "stop",
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

    # Persist trace for non-stream requests
    if not private_build:
        try:
            session_manager = w.get_session_manager()
            session_manager.get_or_create_session("proxy")
            logs_repo = w.get_logs_repository()
            log_metadata = {
                "user_query": user_query[:500],
                "response_preview": content_preview[:500],
                "trace_id": trace_id,
                "model": use_model,
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens_approx,
                "completion_tokens": completion_tokens_approx,
                "total_tokens": _total_tokens_approx,
                "rag_context": rag_context_data,
                "rag_steps": rag_timings,
                "trace": trace,
                "stream": False,
                "is_autocomplete": bool(is_autocomplete),
                "requested_model": requested_model,
                "proxy_backend": proxy_backend_tag(),
            }
            logs_repo.add_log(
                session_id="proxy",
                level="INFO",
                message=f"Proxy request: {user_query[:100]}...",
                source="proxy",
                metadata=log_metadata,
            )
        except Exception as e:
            _RAG_LOG.warning("Failed to log proxy non-stream request to database: %s", e)

    return jsonify(response_data)
