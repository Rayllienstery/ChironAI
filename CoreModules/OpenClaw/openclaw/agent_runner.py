"""Multi-step agent: Ollama native tools + rag_query -> build_rag_context."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Callable

from application.rag.params import RAGAnswerParams, RAGDependencies, get_rag_answer_params
from application.rag.use_cases import build_rag_context
from domain.entities.rag import RagQuestionRequest
from infrastructure.database import get_settings_repository
from infrastructure.ollama.chat_client import normalize_ollama_chat_options
from infrastructure.ollama.openai_ollama_tool_bridge import (
    arguments_to_ollama_object,
    ollama_message_to_openai_assistant,
    ollama_tools_from_openai,
    openai_finish_reason_from_ollama,
    openai_messages_to_ollama,
)

_LOG = logging.getLogger("openclaw.agent")

RAG_QUERY_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "rag_query",
        "description": (
            "Search ChironAI RAG index and return relevant documentation excerpts. "
            "Use a short, focused natural-language query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up in the knowledge base"},
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
    "You are the ChironAI OpenClaw coding agent. "
    "For substantive technical questions (APIs, frameworks, iOS/Swift behavior, architecture), you must call "
    "rag_query at least once with a short, focused query derived from the user's question before your final answer, "
    "then ground your explanation in retrieved excerpts when they are relevant. "
    "Only skip rag_query for pure meta requests (e.g. \"hello\", \"thanks\") with no technical content."
)


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
        "openclaw_pipeline": True,
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


def run_openclaw_chat_completion(
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

    # Some clients (e.g. editors) always send stream=true for OpenAI-compatible APIs.
    # OpenClaw currently returns a single non-streaming completion; ignore the flag for now.
    stream = bool(body.get("stream"))

    # OpenClaw-specific app_settings (collection + default Ollama model).
    configured = ""
    openclaw_collection: str | None = None
    oc_temp_override: float | None = None
    oc_top_p_override: float | None = None
    try:
        repo = get_settings_repository()
        configured = (repo.get_app_setting("openclaw_default_model") or "").strip()
        _oc = (repo.get_app_setting("openclaw_rag_collection") or "").strip()
        openclaw_collection = _oc if _oc else None
        _ts = (repo.get_app_setting("openclaw_chat_temperature") or "").strip()
        if _ts:
            try:
                oc_temp_override = float(_ts)
            except (TypeError, ValueError):
                oc_temp_override = None
        _tp = (repo.get_app_setting("openclaw_chat_top_p") or "").strip()
        if _tp:
            try:
                oc_top_p_override = float(_tp)
            except (TypeError, ValueError):
                oc_top_p_override = None
    except Exception:
        pass

    params: RAGAnswerParams
    deps: RAGDependencies
    params, deps = get_rag_answer_params(
        webui_dir=webui_dir,
        collection_name=openclaw_collection,
    )
    chat_client = deps.chat_client
    ollama_model = configured or params.model_name
    if not str(ollama_model or "").strip():
        # Configuration error: no concrete Ollama model selected for OpenClaw.
        err_msg = "No default Ollama model configured for OpenClaw. Select one in WebUI → Claw Proxy."
        if trace_callback is not None:
            trace_callback(
                {
                    "trace_id": str(uuid.uuid4()),
                    "ts_ms": int(time.time() * 1000),
                    "logical_model_id": logical_model_id,
                    "resolved_model": "",
                    "elapsed_ms": 0,
                    "steps": [
                        {"kind": "config_error", "step": 0, "ok": False, "error": err_msg}
                    ],
                    "step_count": 1,
                    "total_prompt_tokens_est": 0,
                    "total_completion_tokens_est": 0,
                    "final": True,
                    "error": err_msg,
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

    trace_id = str(uuid.uuid4())
    started = time.perf_counter()
    steps_out: list[dict[str, Any]] = []
    total_in = 0
    total_out = 0

    openai_messages: list[dict[str, Any]] = [dict(m) for m in messages if isinstance(m, dict)]
    if not any(m.get("role") in ("system", "developer") for m in openai_messages):
        openai_messages.insert(0, {"role": "system", "content": DEFAULT_AGENT_SYSTEM})

    client_tools = body.get("tools")
    tools_list: list[dict[str, Any]] = [RAG_QUERY_TOOL]
    if isinstance(client_tools, list):
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

    for step_idx in range(max_steps):
        ollama_messages = openai_messages_to_ollama(openai_messages)
        oll_tools = ollama_tools_from_openai(tools_list)
        payload: dict[str, Any] = {
            "model": use_model,
            "messages": ollama_messages,
            "stream": False,
            "options": dict(_co),
        }
        if oll_tools:
            payload["tools"] = oll_tools

        t0 = time.perf_counter()
        try:
            chat_fn = getattr(chat_client, "chat_api", None)
            if not callable(chat_fn):
                return {"error": {"message": "Chat client has no chat_api", "type": "api_error"}}, 500
            data = chat_fn(payload)
        except Exception as e:
            _LOG.exception("openclaw ollama chat_api failed: %s", e)
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
            )
            return {"error": {"message": err, "type": "upstream_error"}}, 502

        oll_msg = data.get("message") if isinstance(data.get("message"), dict) else {}
        openai_assistant = ollama_message_to_openai_assistant(oll_msg)
        pt = _estimate_tokens(ollama_messages)
        ct = _estimate_tokens(openai_assistant.get("content") or oll_msg)
        total_in += pt
        total_out += ct
        tool_calls = openai_assistant.get("tool_calls") if isinstance(openai_assistant.get("tool_calls"), list) else []
        finish = openai_finish_reason_from_ollama(oll_msg)

        steps_out.append(
            {
                "kind": "model_call",
                "step": step_idx,
                "ok": True,
                "duration_ms": dur_ms,
                "model": use_model,
                "finish_reason": finish,
                "prompt_tokens_est": pt,
                "completion_tokens_est": ct,
                "tool_calls_count": len(tool_calls),
            }
        )

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
            )
            return resp, 200

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
                        "note": "OpenClaw only executes rag_query in-tree; pass-through not implemented",
                    }
                )
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name or "unknown",
                        "content": json.dumps({"error": "tool not executed by OpenClaw runtime"}),
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
        error="max_agent_steps exceeded",
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
) -> None:
    if cb is None:
        return
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    rec = {
        "trace_id": trace_id,
        "ts_ms": int(time.time() * 1000),
        "logical_model_id": logical_model_id,
        "resolved_model": resolved_model,
        "elapsed_ms": elapsed_ms,
        "steps": steps,
        "step_count": len(steps),
        "total_prompt_tokens_est": total_in,
        "total_completion_tokens_est": total_out,
        "process_rss_mb": _process_rss_mb(),
        "final": final,
        "error": error,
        "client_model": body.get("model"),
    }
    cb(rec)
