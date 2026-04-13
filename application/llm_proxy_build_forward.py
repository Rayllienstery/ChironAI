"""Forward OpenAI chat to ClawCode for LLM Proxy builds with backend=claw."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Iterator

import requests
from flask import Response, jsonify

from config import get_clawcode_host, get_clawcode_openai_port, get_server_host

_LOG = logging.getLogger(__name__)

_claw_http_session = requests.Session()


def _inject_tester_request_id(payload: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    tid = body.get("tester_request_id") if isinstance(body, dict) else None
    if not isinstance(tid, str) or not tid.strip():
        return payload
    out = dict(payload)
    out.setdefault("tester_request_id", tid.strip())
    return out


def _last_user_query_from_messages(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for m in reversed(messages):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str):
            return c
        if c is None:
            return ""
        try:
            return json.dumps(c, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(c)
    return ""


def _claw_openai_base() -> str:
    env = (os.getenv("CLAWCODE_OPENAI_BASE_URL") or "").strip().rstrip("/")
    if env:
        return env
    host = get_clawcode_host()
    port = get_clawcode_openai_port()
    if host in ("0.0.0.0", "::", ""):
        dh = get_server_host()
        if dh in ("0.0.0.0", "::", ""):
            dh = "127.0.0.1"
        host = dh
    return f"http://{host}:{port}".rstrip("/")


def _trace_id_from_claw_payload(data: dict[str, Any]) -> str | None:
    tid = data.get("trace_id")
    if isinstance(tid, str) and tid.strip():
        return tid.strip()
    return None


def _persist_claw_proxy_log(
    *,
    body: dict[str, Any],
    build: dict[str, Any],
    data: dict[str, Any],
    latency_ms: int,
    stream: bool,
) -> None:
    from infrastructure.database import get_logs_repository
    from infrastructure.database.session_manager import get_session_manager

    bid = str(build.get("id") or "").strip()
    ollama_tag = str(build.get("ollama_model") or "").strip()
    user_q = _last_user_query_from_messages(body.get("messages"))
    content_preview = ""
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message")
            if isinstance(msg, dict):
                c0 = msg.get("content")
                if isinstance(c0, str):
                    content_preview = c0[:500]

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    pt = usage.get("prompt_tokens")
    ct = usage.get("completion_tokens")
    tt = usage.get("total_tokens")

    rag_meta = data.get("rag_metadata")
    rag_context_data = None
    if isinstance(rag_meta, dict):
        chunks = rag_meta.get("chunks_info") or []
        cc = rag_meta.get("chunks_count")
        if cc is None and isinstance(chunks, list):
            cc = len(chunks)
        rag_context_data = {
            "chunks_info": chunks if isinstance(chunks, list) else [],
            "max_score": rag_meta.get("max_score"),
            "chunks_count": int(cc or 0),
        }

    log_model = bid if bid else str(data.get("model") or ollama_tag)
    trace_id = _trace_id_from_claw_payload(data)

    db_path = os.getenv("WEBUI_DB_PATH", "logs/webui.db")
    get_session_manager(db_path).get_or_create_session("proxy")
    logs_repo = get_logs_repository()
    logs_repo.add_log(
        session_id="proxy",
        level="INFO",
        message=f"Proxy request (claw): {user_q[:100]}...",
        source="proxy",
        metadata={
            "user_query": user_q[:500],
            "response_preview": content_preview,
            "model": log_model,
            "requested_model": (str(body.get("model") or "").strip() or log_model),
            "latency_ms": int(data.get("latency_ms") or latency_ms),
            "prompt_tokens": int(pt) if isinstance(pt, (int, float)) else 0,
            "completion_tokens": int(ct) if isinstance(ct, (int, float)) else 0,
            "total_tokens": int(tt) if isinstance(tt, (int, float)) else 0,
            "rag_context": rag_context_data,
            "proxy_backend": "claw",
            "claw_build_id": bid or None,
            "stream": stream,
            "is_autocomplete": False,
            **({"trace_id": trace_id} if trace_id else {}),
        },
    )


def _persist_claw_proxy_log_stream_summary(
    *,
    body: dict[str, Any],
    build: dict[str, Any],
    start_time: float,
    accumulated_text: str,
    trace_id: str | None,
    usage: dict[str, Any] | None,
) -> None:
    """One proxy row after SSE completes; synthesize minimal OpenAI-shaped dict for shared metadata."""
    latency_ms = int((time.time() - start_time) * 1000)
    bid = str(build.get("id") or "").strip()
    ollama_tag = str(build.get("ollama_model") or "").strip()
    log_model = bid if bid else ollama_tag
    user_q = _last_user_query_from_messages(body.get("messages"))
    pt = ct = tt = 0
    if isinstance(usage, dict):
        if isinstance(usage.get("prompt_tokens"), (int, float)):
            pt = int(usage["prompt_tokens"])
        if isinstance(usage.get("completion_tokens"), (int, float)):
            ct = int(usage["completion_tokens"])
        if isinstance(usage.get("total_tokens"), (int, float)):
            tt = int(usage["total_tokens"])
    if tt == 0 and (pt or ct):
        tt = pt + ct

    from infrastructure.database import get_logs_repository
    from infrastructure.database.session_manager import get_session_manager

    db_path = os.getenv("WEBUI_DB_PATH", "logs/webui.db")
    get_session_manager(db_path).get_or_create_session("proxy")
    logs_repo = get_logs_repository()
    logs_repo.add_log(
        session_id="proxy",
        level="INFO",
        message=f"Proxy request (claw stream): {user_q[:100]}...",
        source="proxy",
        metadata={
            "user_query": user_q[:500],
            "response_preview": accumulated_text[:500],
            "model": log_model,
            "requested_model": (str(body.get("model") or "").strip() or log_model),
            "latency_ms": latency_ms,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": tt,
            "rag_context": None,
            "proxy_backend": "claw",
            "claw_build_id": bid or None,
            "stream": True,
            "is_autocomplete": False,
            **({"trace_id": trace_id} if trace_id else {}),
        },
    )


def _process_sse_line(
    line: str,
    *,
    accumulated_content: list[str],
    trace_id_holder: list[str | None],
    usage_holder: list[dict[str, Any] | None],
) -> None:
    s = line.strip()
    if not s.startswith("data:"):
        return
    payload = s[5:].strip()
    if payload == "[DONE]":
        return
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return
    if not isinstance(obj, dict):
        return
    tid = _trace_id_from_claw_payload(obj)
    if tid:
        trace_id_holder[0] = tid
    choices = obj.get("choices")
    if isinstance(choices, list) and choices:
        c0 = choices[0]
        if isinstance(c0, dict):
            delta = c0.get("delta")
            if isinstance(delta, dict):
                c = delta.get("content")
                if isinstance(c, str) and c:
                    accumulated_content.append(c)
            msg = c0.get("message")
            if isinstance(msg, dict):
                c2 = msg.get("content")
                if isinstance(c2, str) and c2:
                    accumulated_content.append(c2)
    u = obj.get("usage")
    if isinstance(u, dict):
        usage_holder[0] = u


def _wrap_sse_stream_with_logging(
    byte_iter: Iterator[bytes],
    *,
    body: dict[str, Any],
    build: dict[str, Any],
    start_time: float,
    persist_log: bool = True,
) -> Iterator[bytes]:
    buf = b""
    accumulated_content: list[str] = []
    trace_id_holder: list[str | None] = [None]
    usage_holder: list[dict[str, Any] | None] = [None]
    try:
        for piece in byte_iter:
            if piece:
                yield piece
                buf += piece
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        _process_sse_line(
                            line.decode("utf-8", errors="replace"),
                            accumulated_content=accumulated_content,
                            trace_id_holder=trace_id_holder,
                            usage_holder=usage_holder,
                        )
                    except Exception:
                        pass
        if buf:
            try:
                _process_sse_line(
                    buf.decode("utf-8", errors="replace"),
                    accumulated_content=accumulated_content,
                    trace_id_holder=trace_id_holder,
                    usage_holder=usage_holder,
                )
            except Exception:
                pass
    finally:
        if persist_log:
            try:
                full_text = "".join(accumulated_content)
                _persist_claw_proxy_log_stream_summary(
                    body=body,
                    build=build,
                    start_time=start_time,
                    accumulated_text=full_text,
                    trace_id=trace_id_holder[0],
                    usage=usage_holder[0],
                )
            except Exception as e:
                _LOG.warning("forward_claw_build_chat: failed to persist proxy log (stream): %s", e)


def forward_claw_build_chat(body: dict[str, Any], build: dict[str, Any]) -> Any:
    """
    POST to ClawCode; the forwarded JSON uses the build's concrete Ollama tag as ``model`` (required).
    ClawCode resolves the upstream model from that field (or from RAG/chat config if ``model`` were empty).

    Extended fields (ChironAI, ignored by stock OpenAI clients): optional ``rag_collection`` and
    ``rag_query_default_top_k`` (merged from the request ``body`` and/or the build). Optional
    ``claw_override_max_agent_steps`` on ``body`` overrides the build's ``max_agent_steps``.
    """
    ollama_tag = str(build.get("ollama_model") or "").strip()
    if not ollama_tag:
        return jsonify(_inject_tester_request_id({"error": "claw build is missing ollama_model"}, body)), 400

    private_build = bool(build.get("private"))
    claw_headers = {"X-Chiron-Private": "1"} if private_build else None

    base = _claw_openai_base()
    forward: dict[str, Any] = {
        "model": ollama_tag,
        "messages": body.get("messages") or [],
    }
    passthrough_keys = (
        "temperature",
        "top_p",
        "tools",
        "tool_choice",
        "stream",
        "merge_client_tools",
        "think",
    )
    for key in passthrough_keys:
        if key in body:
            forward[key] = body[key]

    if "temperature" not in forward and build.get("temperature") is not None:
        try:
            forward["temperature"] = float(build["temperature"])
        except (TypeError, ValueError):
            pass
    if "top_p" not in forward and build.get("top_p") is not None:
        try:
            forward["top_p"] = float(build["top_p"])
        except (TypeError, ValueError):
            pass
    if build.get("chat_think") and "think" not in forward:
        forward["think"] = True

    max_steps_set: int | None = None
    oms = body.get("claw_override_max_agent_steps") if isinstance(body, dict) else None
    if oms is not None and str(oms).strip() != "":
        try:
            n_oms = int(oms)
            if 1 <= n_oms <= 256:
                max_steps_set = n_oms
        except (TypeError, ValueError):
            pass
    if max_steps_set is None:
        ms = build.get("max_agent_steps")
        if ms is not None:
            try:
                n = int(ms)
                if 1 <= n <= 256:
                    max_steps_set = n
            except (TypeError, ValueError):
                pass
    if max_steps_set is not None:
        forward["max_agent_steps"] = max_steps_set

    # Optional RAG routing for ClawCode rag_query: request body overrides, else build profile.
    rc_body = ""
    if isinstance(body, dict):
        _rc = body.get("rag_collection")
        if isinstance(_rc, str):
            rc_body = _rc.strip()
    if rc_body:
        forward["rag_collection"] = rc_body
    else:
        rc_build = str(build.get("rag_collection") or "").strip()
        if rc_build:
            forward["rag_collection"] = rc_build

    rtk_set: int | None = None
    if isinstance(body, dict) and body.get("rag_query_default_top_k") is not None:
        try:
            ntk = int(body["rag_query_default_top_k"])
            if 1 <= ntk <= 256:
                rtk_set = ntk
        except (TypeError, ValueError):
            pass
    if rtk_set is None:
        rtk_b = build.get("rag_top_k")
        if rtk_b is not None and str(rtk_b).strip() != "":
            try:
                ntb = int(rtk_b)
                if 1 <= ntb <= 256:
                    rtk_set = ntb
            except (TypeError, ValueError):
                pass
    if rtk_set is not None:
        forward["rag_query_default_top_k"] = rtk_set

    # Build profile always controls whether ClawCode registers rag_query (ignore client override on this hop).
    forward["include_rag_query_tool"] = bool(build.get("rag_enabled", True))
    forward["include_skill_tools"] = bool(build.get("skills_enabled", True))

    try:
        timeout_sec = float(os.getenv("CLAWCODE_CHAT_TIMEOUT_SEC", "600"))
    except (TypeError, ValueError):
        timeout_sec = 600.0

    start_time = time.time()
    try:
        resp = _claw_http_session.post(
            f"{base}/v1/chat/completions",
            json=forward,
            headers=claw_headers or {},
            timeout=(10.0, timeout_sec),
            stream=True,
        )
    except requests.RequestException as e:
        return jsonify(
            _inject_tester_request_id({"error": f"ClawCode unreachable at {base}: {e}"}, body)
        ), 502

    if resp.status_code >= 400:
        try:
            err_data = resp.json() if resp.content else {}
        except ValueError:
            err_data = {}
        if isinstance(err_data, dict):
            err = err_data.get("error")
            if isinstance(err, dict):
                msg = str(err.get("message") or err)
            else:
                msg = str(err or resp.text or "ClawCode error")
        else:
            msg = str(resp.text or "ClawCode error")
        return jsonify(_inject_tester_request_id({"error": msg}, body)), 502

    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "text/event-stream" in content_type:
        stream_iter = resp.iter_content(chunk_size=None)

        def gen() -> Iterator[bytes]:
            yield from _wrap_sse_stream_with_logging(
                stream_iter,
                body=body,
                build=build,
                start_time=start_time,
                persist_log=not private_build,
            )

        return Response(
            gen(),
            status=resp.status_code,
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        return jsonify(
            _inject_tester_request_id({"error": "ClawCode returned non-JSON response"}, body)
        ), 502

    latency_ms = int((time.time() - start_time) * 1000)
    if "latency_ms" not in data:
        data["latency_ms"] = latency_ms

    # Report build id to client (OpenAI model field)
    bid = str(build.get("id") or "").strip()
    if bid:
        data["model"] = bid

    include_rag_metadata = body.get("include_rag_metadata", True)
    if not include_rag_metadata:
        data.pop("rag_metadata", None)

    if private_build:
        data.pop("trace_id", None)

    if not private_build:
        try:
            _persist_claw_proxy_log(
                body=body,
                build=build,
                data=data,
                latency_ms=latency_ms,
                stream=bool(body.get("stream")),
            )
        except Exception as e:
            _LOG.warning("forward_claw_build_chat: failed to persist proxy log: %s", e)

    data = _inject_tester_request_id(data, body)
    return jsonify(data), 200
