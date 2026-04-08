"""Multi-step agent: Ollama native tools + rag_query -> build_rag_context."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Callable

try:
    from chironai_rag.consumers import CLAWCODE_RAG_COLLECTION_APP_SETTING
except ImportError:
    CLAWCODE_RAG_COLLECTION_APP_SETTING = "clawcode_rag_collection"

from application.rag.params import RAGAnswerParams, RAGDependencies, get_rag_answer_params
from application.rag.use_cases import build_rag_context
from config import (
    get_clawcode_merge_client_tools as _get_clawcode_merge_client_tools,
    get_clawcode_think_num_predict_floor,
)
from infrastructure.database import get_settings_repository
from infrastructure.ollama.chat_client import normalize_ollama_chat_options
from infrastructure.ollama.model_capabilities import (
    chat_error_suggests_no_think,
    chat_error_suggests_no_tools,
    caps_supports_thinking,
    caps_supports_tools,
    get_cached_ollama_capabilities,
    ollama_native_think_troublesome_model,
)
from infrastructure.ollama.openai_ollama_tool_bridge import (
    arguments_to_ollama_object,
    ollama_message_to_openai_assistant,
    ollama_tools_from_openai,
    openai_finish_reason_from_ollama,
    openai_messages_to_ollama,
)

_LOG = logging.getLogger("clawcode.agent")

# Per-field caps for trace / DB metadata (avoid huge SQLite rows).
_TRACE_FIELD_CAP = 48_000
_TRACE_MSG_CAP = 12_000
_TRACE_TOOL_ARGS_CAP = 4_000

RAG_QUERY_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "rag_query",
        "description": (
            "Search the ChironAI **indexed knowledge base** (ingested documentation and similar material) and "
            "return excerpts. This is **not** a search over the user's live workspace or repo files unless those "
            "files were explicitly ingested into RAG. Use a short, focused natural-language query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Topic to look up in the indexed knowledge base (not a file path or repo scan)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Optional; number of chunks (server may cap)",
                },
            },
            "required": ["query"],
        },
    },
}

DEFAULT_AGENT_SYSTEM = (
    "You are the ChironAI ClawCode coding agent. "
    "rag_query searches an indexed knowledge base (docs, ingested texts)—it does not read arbitrary files from "
    "the user's open project unless that content was ingested. Do not treat RAG hits as the user's application "
    "source code or assume the workspace is fully covered by RAG. "
    "For substantive technical questions (APIs, frameworks, iOS/Swift behavior, architecture), call rag_query "
    "at least once with a short, focused query when that knowledge could help, then ground your answer in excerpts "
    "when relevant. Skip rag_query for pure meta requests (e.g. \"hello\", \"thanks\") or when the task is only "
    "about locating or editing specific files in the workspace and RAG would not substitute for filesystem access."
)

# Injected after the first system/developer message so clients that already send a large system prompt (e.g. Copilot)
# still see ClawCode runtime rules.
RUNTIME_DEVELOPER_RAG_ONLY = (
    "ClawCode runtime (server-side tools): Only rag_query runs here. It queries the **indexed knowledge base**, "
    "not the user's live workspace tree—do not claim RAG returned or failed to return their project source files. "
    "IDE tools (semantic_search, list_dir, read_file, grep_search, etc.) are unavailable in this session; you "
    "cannot scan or open repo files from the server. If the user needs to find or edit UI/code in their project, "
    "state honestly that this mode has no filesystem access and they should enable IDE mode (merge_client_tools) for "
    "ClawCode (see docs) so the IDE can run tools, or work from files already shown in the chat context. "
    "Use rag_query only when ingested documentation or similar reference material could help; it is not a "
    "replacement for listing or searching their repository. "
    "If you use tools in this session, call **only** the rag_query function—any other tool name is invalid and "
    "will be rejected. When speaking to the user, do not recite internal tool identifiers; say things like "
    "\"workspace search in the editor\" or \"enable IDE tool pass-through in ClawCode settings\" instead."
)

RUNTIME_DEVELOPER_MERGE_CLIENT_TOOLS = (
    "ClawCode runtime: rag_query searches the indexed knowledge base, not the live workspace unless ingested; "
    "use IDE tools when you need actual project files. rag_query runs on the server; IDE tools run in the client "
    "when returned as tool_calls. Do not mix rag_query and other tools in the same assistant tool_calls batch—"
    "use only rag_query in one turn, or only IDE tools in another so the client can execute them. "
    "VS Code / Copilot does not expose a tool named `search`; for text search in files call **grep_search** with "
    "`query` (and optional `includePattern`, `isRegexp`, `maxResults`). "
    "Use absolute paths from the workspace; in this monorepo UI code often lives under **CoreModules/** "
    "(e.g. CoreModules/CoreUI/src/…)—avoid shortening to CoreUI/… if that path does not exist at the repo root. "
    "When using replace_string_in_file, the old_string must match the file exactly, including Windows CRLF line "
    "endings if that is what read_file returned; after a failed replace, re-read the file and copy the snippet verbatim "
    "or use insert_edit_into_file with // ...existing code... anchors."
)


def _tool_call_names(tool_calls: list[Any]) -> list[str]:
    names: list[str] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        names.append(str(fn.get("name") or "") if isinstance(fn, dict) else "")
    return names


def _client_registered_tool_names_lower(body: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    tools = body.get("tools")
    if not isinstance(tools, list):
        return out
    for t in tools:
        if not isinstance(t, dict) or t.get("type") != "function":
            continue
        fn = t.get("function")
        if isinstance(fn, dict):
            n = fn.get("name")
            if isinstance(n, str) and n.strip():
                out.add(n.strip().lower())
    return out


def _normalize_grep_search_arguments(raw_args: Any) -> dict[str, Any]:
    """Map common mistaken `search` payloads into grep_search-shaped JSON."""
    obj: dict[str, Any]
    if isinstance(raw_args, dict):
        obj = dict(raw_args)
    elif isinstance(raw_args, str) and raw_args.strip():
        try:
            parsed = json.loads(raw_args)
            obj = dict(parsed) if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            obj = {}
    else:
        obj = {}
    query = (
        obj.get("query")
        or obj.get("pattern")
        or obj.get("q")
        or obj.get("text")
        or obj.get("search")
        or ""
    )
    query = str(query).strip()
    inc = (
        obj.get("includePattern")
        or obj.get("path")
        or obj.get("file")
        or obj.get("file_path")
        or obj.get("glob")
        or ""
    )
    inc = str(inc).strip() if inc else ""
    is_reg = obj.get("isRegexp", obj.get("regexp", False))
    if not isinstance(is_reg, bool):
        is_reg = str(is_reg).lower() in ("1", "true", "yes")
    try:
        max_res = int(obj.get("maxResults", 20))
    except (TypeError, ValueError):
        max_res = 20
    max_res = max(1, min(max_res, 500))
    out: dict[str, Any] = {"query": query, "isRegexp": is_reg, "maxResults": max_res}
    if inc:
        out["includePattern"] = inc
    return out


def _alias_search_tool_calls_to_grep_search(assistant_msg: dict[str, Any], body: dict[str, Any]) -> None:
    """
    Some models emit tool name `search`, which VS Code does not register (use grep_search).
    Rewrite pass-through tool_calls so the IDE can execute them when grep_search is available.
    """
    reg = _client_registered_tool_names_lower(body)
    if "grep_search" not in reg:
        return
    tcs = assistant_msg.get("tool_calls")
    if not isinstance(tcs, list):
        return
    for tc in tcs:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function")
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "").strip().lower()
        if name != "search":
            continue
        fn["name"] = "grep_search"
        normalized = _normalize_grep_search_arguments(fn.get("arguments"))
        try:
            fn["arguments"] = json.dumps(normalized, ensure_ascii=False)
        except (TypeError, ValueError):
            fn["arguments"] = "{}"


def _inject_clawcode_runtime_context(
    openai_messages: list[dict[str, Any]],
    *,
    merge_client_tools: bool,
) -> None:
    has_sd = any(
        isinstance(m, dict) and m.get("role") in ("system", "developer") for m in openai_messages
    )
    if not has_sd:
        openai_messages.insert(0, {"role": "system", "content": DEFAULT_AGENT_SYSTEM})
    hint = RUNTIME_DEVELOPER_MERGE_CLIENT_TOOLS if merge_client_tools else RUNTIME_DEVELOPER_RAG_ONLY
    insert_at = 0
    for i, m in enumerate(openai_messages):
        if isinstance(m, dict) and m.get("role") in ("system", "developer"):
            insert_at = i + 1
            break
    openai_messages.insert(insert_at, {"role": "developer", "content": hint})


def _sanitize_chunks_for_metadata(chunks: list[dict[str, Any]], *, per_call_limit: int = 24) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, c in enumerate((chunks or [])[:per_call_limit]):
        if not isinstance(c, dict):
            continue
        preview = (c.get("text_preview") or c.get("text") or "")[:900]
        out.append(
            {
                "index": c.get("index", i + 1),
                "score": c.get("score"),
                "rerank_score": c.get("rerank_score"),
                "url": c.get("url"),
                "source": c.get("source") or c.get("doc_type"),
                "text_preview": preview,
            }
        )
    return out


def _rag_metadata_from_agent_steps(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize rag_query tool calls for WebUI / RAG test validation (chunks_count, etc.)."""
    tool_rag = [s for s in steps if isinstance(s, dict) and s.get("kind") == "tool_rag"]
    n_chunks = sum(int(s.get("chunks") or 0) for s in tool_rag)
    max_score = 0.0
    for s in tool_rag:
        try:
            max_score = max(max_score, float(s.get("max_score") or 0))
        except (TypeError, ValueError):
            pass
    ctx_chars = sum(int(s.get("context_chars") or 0) for s in tool_rag)
    merged_chunks: list[dict[str, Any]] = []
    rag_queries: list[dict[str, Any]] = []
    for s in tool_rag:
        q = str(s.get("query") or "").strip()
        if q:
            rag_queries.append(
                {
                    "query": q,
                    "step": s.get("step"),
                    "chunks": int(s.get("chunks") or 0),
                    "ok": s.get("ok"),
                    "error": s.get("error"),
                }
            )
        for ch in _sanitize_chunks_for_metadata(list(s.get("chunks_info") or [])):
            merged_chunks.append(ch)
    return {
        "chunks_info": merged_chunks,
        "chunks_count": n_chunks,
        "max_score": max_score,
        "context_chars": ctx_chars,
        "rag_queries": rag_queries,
        "clawcode_pipeline": True,
    }


def _estimate_tokens(obj: Any) -> int:
    try:
        return max(1, len(json.dumps(obj, ensure_ascii=False)) // 4)
    except (TypeError, ValueError):
        return 1


def _process_rss_mb() -> float | None:
    try:
        import psutil

        return round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2)
    except Exception:
        return None


def _cap_trace_text(s: object | None, limit: int) -> tuple[str, bool]:
    if s is None:
        return "", False
    t = s if isinstance(s, str) else str(s)
    if len(t) <= limit:
        return t, False
    return t[:limit] + "\n…[truncated]", True


def _openai_content_preview(msg: dict[str, Any]) -> str:
    c = msg.get("content")
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    try:
        return json.dumps(c, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(c)


def _compact_tool_calls_for_trace(openai_assistant: dict[str, Any]) -> list[dict[str, Any]]:
    tcs = openai_assistant.get("tool_calls")
    if not isinstance(tcs, list):
        return []
    out: list[dict[str, Any]] = []
    for tc in tcs:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = str(fn.get("name") or "") if isinstance(fn, dict) else ""
        raw_args = fn.get("arguments") if isinstance(fn, dict) else None
        if isinstance(raw_args, str):
            arg_s = raw_args
        else:
            try:
                arg_s = json.dumps(raw_args, ensure_ascii=False) if raw_args is not None else ""
            except (TypeError, ValueError):
                arg_s = str(raw_args)
        arg_s, arg_trunc = _cap_trace_text(arg_s, _TRACE_TOOL_ARGS_CAP)
        out.append(
            {
                "id": str(tc.get("id") or ""),
                "name": name,
                "arguments": arg_s,
                "arguments_truncated": arg_trunc,
            }
        )
    return out


def _trace_request_summary(body: dict[str, Any]) -> dict[str, Any]:
    """Sanitized request snapshot for traces (no full tool schemas)."""
    raw_msgs = body.get("messages")
    msgs_out: list[dict[str, Any]] = []
    if isinstance(raw_msgs, list):
        for m in raw_msgs:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "")
            text, trunc = _cap_trace_text(_openai_content_preview(m), _TRACE_MSG_CAP)
            entry: dict[str, Any] = {"role": role, "content": text, "content_truncated": trunc}
            if m.get("name"):
                entry["name"] = str(m.get("name"))
            if m.get("tool_call_id"):
                entry["tool_call_id"] = str(m.get("tool_call_id"))
            msgs_out.append(entry)
    tools = body.get("tools")
    tool_names: list[str] = []
    if isinstance(tools, list):
        for t in tools:
            if not isinstance(t, dict) or t.get("type") != "function":
                continue
            fn = t.get("function")
            if isinstance(fn, dict) and fn.get("name"):
                tool_names.append(str(fn.get("name")))
    return {
        "model": body.get("model"),
        "stream": bool(body.get("stream")),
        "messages": msgs_out,
        "client_tool_names": tool_names,
    }


def _coerce_positive_int(v: object) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _coerce_nonneg_int(v: object) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _apply_clawcode_num_predict_budget(
    opts: dict[str, Any],
    body: dict[str, Any],
    *,
    think_requested: bool,
) -> dict[str, Any]:
    """
    Merge OpenAI max_tokens / max_completion_tokens into Ollama num_predict, then apply think floor.
    """
    out = dict(opts)
    cur = _coerce_positive_int(out.get("num_predict"))
    cur_i = cur if cur is not None else 0

    mt = body.get("max_tokens")
    if mt is None:
        mt = body.get("max_completion_tokens")
    client_n = _coerce_positive_int(mt)
    if client_n is not None:
        out["num_predict"] = max(cur_i, client_n)
        cur_i = out["num_predict"]

    if think_requested:
        floor = get_clawcode_think_num_predict_floor()
        out["num_predict"] = max(cur_i, floor)

    return out


def _ollama_trace_counts(data: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    """Root-level Ollama /api/chat fields for traces."""
    dr_raw = data.get("done_reason")
    if dr_raw is None:
        ollama_dr: str | None = None
    elif isinstance(dr_raw, str):
        ollama_dr = dr_raw.strip() or None
    else:
        ollama_dr = str(dr_raw).strip() or None

    pec = _coerce_nonneg_int(data.get("prompt_eval_count"))
    ec = _coerce_nonneg_int(data.get("eval_count"))
    return ollama_dr, pec, ec


def run_clawcode_chat_completion(
    body: dict[str, Any],
    *,
    webui_dir: str | None,
    max_steps: int,
    logical_model_id: str,
    trace_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], int]:
    """
    Run agent loop; return (openai_chat_completion_dict, http_status).
    """
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return {"error": {"message": "messages required", "type": "invalid_request_error"}}, 400

    _body_mc = body.get("merge_client_tools")
    merge_client_tools = (
        bool(_body_mc) if isinstance(_body_mc, bool) else _get_clawcode_merge_client_tools()
    )

    # Some clients (e.g. VS Code Copilot) send stream=true. The HTTP layer turns the final
    # completion into OpenAI SSE; the agent loop still produces one assembled message.

    # ClawCode-specific app_settings (collection + default Ollama model).
    configured = ""
    clawcode_collection: str | None = None
    oc_temp_override: float | None = None
    oc_top_p_override: float | None = None
    oc_think_request = False
    try:
        repo = get_settings_repository()
        configured = (repo.get_app_setting("clawcode_default_model") or "").strip()
        _oc = (repo.get_app_setting(CLAWCODE_RAG_COLLECTION_APP_SETTING) or "").strip()
        clawcode_collection = _oc if _oc else None
        _ts = (repo.get_app_setting("clawcode_chat_temperature") or "").strip()
        if _ts:
            try:
                oc_temp_override = float(_ts)
            except (TypeError, ValueError):
                oc_temp_override = None
        _tp = (repo.get_app_setting("clawcode_chat_top_p") or "").strip()
        if _tp:
            try:
                oc_top_p_override = float(_tp)
            except (TypeError, ValueError):
                oc_top_p_override = None
        _th = (repo.get_app_setting("clawcode_chat_think") or "").strip().lower()
        oc_think_request = _th in ("1", "true", "yes")
    except Exception:
        pass

    params: RAGAnswerParams
    deps: RAGDependencies
    params, deps = get_rag_answer_params(
        webui_dir=webui_dir,
        collection_name=clawcode_collection,
    )
    chat_client = deps.chat_client
    ollama_model = configured or params.model_name
    if not str(ollama_model or "").strip():
        # Configuration error: no concrete Ollama model selected for ClawCode.
        err_msg = "No default Ollama model configured for ClawCode. Select one in WebUI → Claw Proxy."
        if trace_callback is not None:
            trace_callback(
                {
                    "trace_id": str(uuid.uuid4()),
                    "ts_ms": int(time.time() * 1000),
                    "logical_model_id": logical_model_id,
                    "resolved_model": "",
                    "elapsed_ms": 0,
                    "request": {
                        **_trace_request_summary(body),
                        "merge_client_tools": merge_client_tools,
                    },
                    "think_requested": oc_think_request,
                    "steps": [
                        {"kind": "config_error", "step": 0, "ok": False, "error": err_msg}
                    ],
                    "step_count": 1,
                    "total_prompt_tokens_est": 0,
                    "total_completion_tokens_est": 0,
                    "final": True,
                    "error": err_msg,
                    "client_model": body.get("model"),
                }
            )
        return {
            "error": {
                "message": err_msg,
                "type": "model_not_configured",
            }
        }, 400
    requested = body.get("model")
    use_model = ollama_model
    if isinstance(requested, str) and requested.strip() and requested.strip() != logical_model_id:
        use_model = requested.strip()

    _ollama_caps: frozenset[str] | None = None
    try:
        _cu = getattr(chat_client, "_url", None)
        if isinstance(_cu, str) and _cu.strip():
            _ollama_caps = get_cached_ollama_capabilities(use_model.strip(), _cu.strip())
    except Exception:
        _ollama_caps = None

    tools_to_ollama = True
    if _ollama_caps is not None and not caps_supports_tools(_ollama_caps):
        tools_to_ollama = False

    send_think = bool(oc_think_request) and not ollama_native_think_troublesome_model(use_model)
    if _ollama_caps is not None and not caps_supports_thinking(_ollama_caps):
        send_think = False

    trace_id = str(uuid.uuid4())
    started = time.perf_counter()
    steps_out: list[dict[str, Any]] = []
    total_in = 0
    total_out = 0

    openai_messages: list[dict[str, Any]] = [dict(m) for m in messages if isinstance(m, dict)]
    _inject_clawcode_runtime_context(openai_messages, merge_client_tools=merge_client_tools)

    client_tools = body.get("tools")
    tools_list: list[dict[str, Any]] = [RAG_QUERY_TOOL]
    if merge_client_tools and isinstance(client_tools, list):
        for t in client_tools:
            if isinstance(t, dict) and t.get("type") == "function":
                fn = t.get("function")
                if isinstance(fn, dict) and fn.get("name") == "rag_query":
                    continue
                tools_list.append(t)

    _co: dict[str, Any] = dict(getattr(chat_client, "_default_options", None) or {})
    if oc_temp_override is not None:
        _co["temperature"] = oc_temp_override
    if oc_top_p_override is not None:
        _co["top_p"] = oc_top_p_override
    _co = normalize_ollama_chat_options(_co)
    _co = _apply_clawcode_num_predict_budget(_co, body, think_requested=bool(send_think and oc_think_request))

    for step_idx in range(max_steps):
        ollama_messages = openai_messages_to_ollama(openai_messages)
        oll_tools = ollama_tools_from_openai(tools_list) if tools_to_ollama else None
        payload: dict[str, Any] = {
            "model": use_model,
            "messages": ollama_messages,
            "stream": False,
            "options": dict(_co),
        }
        if oll_tools:
            payload["tools"] = oll_tools
        if send_think:
            payload["think"] = True

        t0 = time.perf_counter()
        try:
            chat_fn = getattr(chat_client, "chat_api", None)
            if not callable(chat_fn):
                return {"error": {"message": "Chat client has no chat_api", "type": "api_error"}}, 500
            attempt = dict(payload)
            last_exc: Exception | None = None
            data: dict[str, Any] = {}
            for _ in range(3):
                try:
                    data = chat_fn(attempt)
                    last_exc = None
                    break
                except Exception as e:
                    last_exc = e
                    if chat_error_suggests_no_tools(e) and attempt.pop("tools", None) is not None:
                        tools_to_ollama = False
                        continue
                    if chat_error_suggests_no_think(e) and attempt.pop("think", None) is not None:
                        send_think = False
                        continue
                    break
            if last_exc is not None:
                raise last_exc
        except Exception as e:
            _LOG.exception("clawcode ollama chat_api failed: %s", e)
            err = str(e)
            steps_out.append(
                {
                    "kind": "model_call",
                    "step": step_idx,
                    "ok": False,
                    "error": err,
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                    "model": use_model,
                }
            )
            _emit_trace(
                trace_callback,
                trace_id,
                body,
                steps_out,
                started,
                use_model,
                logical_model_id,
                total_in,
                total_out,
                error=err,
                think_requested=oc_think_request,
                merge_client_tools=merge_client_tools,
            )
            return {"error": {"message": err, "type": "api_error"}}, 502

        dur_ms = int((time.perf_counter() - t0) * 1000)
        err_obj = data.get("error")
        if err_obj:
            err = str(err_obj)
            steps_out.append(
                {
                    "kind": "model_call",
                    "step": step_idx,
                    "ok": False,
                    "error": err,
                    "duration_ms": dur_ms,
                    "model": use_model,
                }
            )
            _emit_trace(
                trace_callback,
                trace_id,
                body,
                steps_out,
                started,
                use_model,
                logical_model_id,
                total_in,
                total_out,
                error=err,
                think_requested=oc_think_request,
                merge_client_tools=merge_client_tools,
            )
            return {"error": {"message": err, "type": "upstream_error"}}, 502

        oll_msg = data.get("message") if isinstance(data.get("message"), dict) else {}
        ollama_dr, ollama_pec, ollama_ec = _ollama_trace_counts(data if isinstance(data, dict) else {})
        openai_assistant = ollama_message_to_openai_assistant(oll_msg)
        if merge_client_tools:
            _alias_search_tool_calls_to_grep_search(openai_assistant, body)
        pt = _estimate_tokens(ollama_messages)
        ct = _estimate_tokens(openai_assistant.get("content") or oll_msg)
        total_in += pt
        total_out += ct
        tool_calls = openai_assistant.get("tool_calls") if isinstance(openai_assistant.get("tool_calls"), list) else []
        finish = openai_finish_reason_from_ollama(oll_msg, ollama_dr)

        th_raw, th_trunc = _cap_trace_text(oll_msg.get("thinking"), _TRACE_FIELD_CAP)
        co_raw, co_trunc = _cap_trace_text(oll_msg.get("content"), _TRACE_FIELD_CAP)
        vis, vis_trunc = _cap_trace_text(_openai_content_preview(openai_assistant), _TRACE_FIELD_CAP)
        tc_compact = _compact_tool_calls_for_trace(openai_assistant)

        step_rec: dict[str, Any] = {
            "kind": "model_call",
            "step": step_idx,
            "ok": True,
            "duration_ms": dur_ms,
            "model": use_model,
            "finish_reason": finish,
            "ollama_done_reason": ollama_dr,
            "prompt_tokens_est": pt,
            "completion_tokens_est": ct,
            "tool_calls_count": len(tool_calls),
            "thinking_raw": th_raw,
            "thinking_truncated": th_trunc,
            "assistant_content_raw": co_raw,
            "assistant_content_raw_truncated": co_trunc,
            "assistant_visible": vis,
            "assistant_visible_truncated": vis_trunc,
            "tool_calls": tc_compact,
        }
        if ollama_pec is not None:
            step_rec["ollama_prompt_eval_count"] = ollama_pec
        if ollama_ec is not None:
            step_rec["ollama_eval_count"] = ollama_ec
        steps_out.append(step_rec)

        if not tool_calls:
            openai_messages.append(openai_assistant)
            resp = _openai_completion_response(
                openai_assistant,
                use_model,
                finish,
                trace_id,
                rag_metadata=_rag_metadata_from_agent_steps(steps_out),
            )
            _emit_trace(
                trace_callback,
                trace_id,
                body,
                steps_out,
                started,
                use_model,
                logical_model_id,
                total_in,
                total_out,
                final=True,
                final_assistant=openai_assistant,
                finish_reason=finish,
                think_requested=oc_think_request,
                merge_client_tools=merge_client_tools,
            )
            return resp, 200

        tc_names = _tool_call_names(tool_calls)
        if merge_client_tools and tc_names and all(n != "rag_query" for n in tc_names):
            steps_out.append(
                {
                    "kind": "tool_pass_through",
                    "step": step_idx,
                    "names": tc_names,
                }
            )
            resp = _openai_completion_response(
                openai_assistant,
                use_model,
                "tool_calls",
                trace_id,
                rag_metadata=_rag_metadata_from_agent_steps(steps_out),
            )
            _emit_trace(
                trace_callback,
                trace_id,
                body,
                steps_out,
                started,
                use_model,
                logical_model_id,
                total_in,
                total_out,
                final=True,
                final_assistant=openai_assistant,
                finish_reason="tool_calls",
                think_requested=oc_think_request,
                merge_client_tools=merge_client_tools,
            )
            return resp, 200

        if merge_client_tools and tc_names and any(n == "rag_query" for n in tc_names) and any(
            n != "rag_query" for n in tc_names
        ):
            _LOG.warning(
                "clawcode: mixed rag_query and client tools in one assistant turn (step=%s); "
                "server executes rag_query only; other tools get stub tool messages",
                step_idx,
            )

        openai_messages.append(openai_assistant)
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = str(fn.get("name") or "") if isinstance(fn, dict) else ""
            call_id = str(tc.get("id") or f"call_{uuid.uuid4().hex[:24]}")
            args = arguments_to_ollama_object(fn.get("arguments") if isinstance(fn, dict) else None)
            if name == "rag_query":
                q = str(args.get("query") or "").strip()
                tr = time.perf_counter()
                ctx_text = ""
                chunk_n = 0
                score = 0.0
                err_rag = None
                chunks_meta: list[dict[str, Any]] = []
                try:
                    if not q:
                        ctx_text = ""
                    else:
                        ctx, _timings = build_rag_context(
                            q,
                            deps.rag_repo,
                            deps.embed_provider,
                            deps.rerank_client,
                            params.context_chunk_chars,
                            params.context_total_chars,
                        )
                        ctx_text = ctx.context_text
                        chunk_n = len(ctx.chunks_info)
                        score = float(ctx.max_score)
                        chunks_meta = _sanitize_chunks_for_metadata(list(ctx.chunks_info or []))
                except Exception as e:
                    _LOG.exception("rag_query failed: %s", e)
                    err_rag = str(e)
                    ctx_text = f"[rag_query error] {err_rag}"
                    chunks_meta = []
                steps_out.append(
                    {
                        "kind": "tool_rag",
                        "step": step_idx,
                        "query": q[:500],
                        "duration_ms": int((time.perf_counter() - tr) * 1000),
                        "chunks": chunk_n,
                        "max_score": score,
                        "ok": err_rag is None,
                        "error": err_rag,
                        "context_chars": len(ctx_text),
                        "chunks_info": chunks_meta,
                    }
                )
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": "rag_query",
                        "content": ctx_text[: params.context_total_chars + 2000],
                    }
                )
            else:
                steps_out.append(
                    {
                        "kind": "tool_unhandled",
                        "name": name,
                        "step": step_idx,
                        "note": (
                            "ClawCode only executes rag_query in-tree; set merge_client_tools and use "
                            "client-only tool batches for IDE pass-through"
                        ),
                    }
                )
                stub = {"error": "tool not executed by ClawCode runtime"}
                if not merge_client_tools:
                    stub["hint"] = (
                        "Only rag_query is registered in this mode. Call rag_query with a short query, or answer "
                        "from the conversation without tools."
                    )
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name or "unknown",
                        "content": json.dumps(stub),
                    }
                )

        # Live WebUI buffer: in-flight snapshot so clients can show final=False before the next step.
        _emit_trace(
            trace_callback,
            trace_id,
            body,
            steps_out,
            started,
            use_model,
            logical_model_id,
            total_in,
            total_out,
            final=False,
            think_requested=oc_think_request,
            merge_client_tools=merge_client_tools,
        )

    _emit_trace(
        trace_callback,
        trace_id,
        body,
        steps_out,
        started,
        use_model,
        logical_model_id,
        total_in,
        total_out,
        error="max_agent_steps exceeded",
        think_requested=oc_think_request,
        merge_client_tools=merge_client_tools,
    )
    return {
        "error": {
            "message": f"max agent steps ({max_steps}) exceeded",
            "type": "agent_limit",
        }
    }, 400


def _openai_completion_response(
    assistant_msg: dict[str, Any],
    model: str,
    finish_reason: str,
    trace_id: str,
    *,
    rag_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "trace_id": trace_id,
        "choices": [
            {
                "index": 0,
                "message": assistant_msg,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
    if rag_metadata:
        out["rag_metadata"] = rag_metadata
    return out


def _emit_trace(
    cb: Callable[[dict[str, Any]], None] | None,
    trace_id: str,
    body: dict[str, Any],
    steps: list[dict[str, Any]],
    started: float,
    resolved_model: str,
    logical_model_id: str,
    total_in: int,
    total_out: int,
    *,
    final: bool = False,
    error: str | None = None,
    final_assistant: dict[str, Any] | None = None,
    finish_reason: str | None = None,
    think_requested: bool = False,
    merge_client_tools: bool | None = None,
) -> None:
    if cb is None:
        return
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    req_summary = _trace_request_summary(body)
    if merge_client_tools is not None:
        req_summary = {**req_summary, "merge_client_tools": merge_client_tools}
    rec: dict[str, Any] = {
        "trace_id": trace_id,
        "ts_ms": int(time.time() * 1000),
        "logical_model_id": logical_model_id,
        "resolved_model": resolved_model,
        "elapsed_ms": elapsed_ms,
        "request": req_summary,
        "think_requested": think_requested,
        "steps": steps,
        "step_count": len(steps),
        "total_prompt_tokens_est": total_in,
        "total_completion_tokens_est": total_out,
        "process_rss_mb": _process_rss_mb(),
        "final": final,
        "error": error,
        "client_model": body.get("model"),
    }
    if final and final_assistant is not None:
        fa = dict(final_assistant)
        raw_c = fa.get("content")
        if raw_c is not None and not isinstance(raw_c, str):
            try:
                raw_c = json.dumps(raw_c, ensure_ascii=False)
            except (TypeError, ValueError):
                raw_c = str(raw_c)
        fc, ftrunc = _cap_trace_text(raw_c, _TRACE_FIELD_CAP)
        rec["final_message"] = {
            "role": str(fa.get("role") or "assistant"),
            "content": fc,
            "content_truncated": ftrunc,
            "finish_reason": finish_reason,
        }
    cb(rec)
