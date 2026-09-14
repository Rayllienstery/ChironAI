"""Initial ``trace['request']`` payload for chat completions."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from llm_proxy.tool_helpers import _extract_tool_name

_PROXY_TRACE_META_KEYS = frozenset(
    {
        "proxy_v1_route",
        "responses_client_stream",
        "incoming_request_id",
        "responses_previous_response_id",
    }
)


def build_chat_trace_request_dict(
    *,
    requested_model: str,
    actual_model: str,
    stream: bool,
    build_sse_streaming: bool,
    chat_max_tokens: int | None,
    effective_num_predict: int | None,
    effective_num_ctx: int | None,
    include_rag_metadata: bool,
    tools: list[Any],
    selected_edit_tool_name: str | None,
    selected_edit_tool: dict[str, Any] | None,
    tool_choice: Any,
    tool_choice_effective: Any,
    has_tool_result: bool,
    tool_result_indicates_failure: bool,
    post_tool_success_turn: bool,
    last_tool_content: str,
    force_rag: bool,
    fetch_web_knowledge: bool,
    fetch_web_knowledge_source: str,
    explicit_reasoning: Any,
    reasoning_level: Any,
    reasoning_for_prompt: Any,
    user_query: str,
    is_autocomplete: bool,
    testing_disable_rerank: bool,
    client_request_id: Any,
) -> dict[str, Any]:
    """Build the base ``trace['request']`` dict before RAG/model-specific fields."""
    return {
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
        "client_request_id": str(client_request_id or "").strip() or None,
    }


def enrich_chat_trace_request(
    trace: dict[str, Any],
    *,
    input_budget: dict[str, Any] | None,
    effective_max_agent_steps: int | None,
    tool_loop_limit_reached: bool,
    trace_chain_id: str | None,
    trace_chain_source: str | None,
    tool_loop_stats: dict[str, Any] | None,
    proxy_trace_meta: dict[str, Any] | None,
    body: dict[str, Any],
    append_trace_warning: Any,
) -> None:
    """Attach optional request trace fields after the base dict is stored."""
    request = trace.setdefault("request", {})
    if input_budget is not None:
        request["input_budget"] = dict(input_budget)
    if effective_max_agent_steps is not None:
        request["effective_max_agent_steps"] = effective_max_agent_steps
    if tool_loop_limit_reached:
        request["tool_loop_limit_reached"] = True
        request["tools_suppressed_for_step_limit"] = True
        append_trace_warning(trace, "tool_loop_limit_reached")
    if trace_chain_id:
        request["trace_chain_id"] = trace_chain_id
        request["trace_chain_source"] = trace_chain_source
    if tool_loop_stats is not None:
        request["tool_loop_stats"] = tool_loop_stats
    if proxy_trace_meta:
        for key, value in proxy_trace_meta.items():
            if key in _PROXY_TRACE_META_KEYS:
                request[key] = value
    if body.get("tools_count_raw") is not None:
        request["tools_count_raw"] = body.get("tools_count_raw")
    if body.get("tools_count_normalized") is not None:
        request["tools_count_normalized"] = body.get("tools_count_normalized")
    if isinstance(body.get("tools_types_raw"), list):
        request["tools_types_raw"] = body.get("tools_types_raw")
    if isinstance(body.get("tools_types_dropped"), list):
        request["tools_types_dropped"] = body.get("tools_types_dropped")
    if isinstance(body.get("tools_types_normalized"), list):
        request["tools_types_normalized"] = body.get("tools_types_normalized")
    if body.get("tool_choice_raw") is not None:
        request["tool_choice_raw"] = body.get("tool_choice_raw")
    if body.get("tool_choice_normalized") is not None:
        request["tool_choice_normalized"] = body.get("tool_choice_normalized")


_WEB_SOURCE_TOOLS = frozenset({"web_search", "web_extract"})
_WEB_SOURCE_URL_KEYS = frozenset({"url", "href", "link"})
_WEB_SOURCE_NEST_KEYS = frozenset({"urls", "web", "results", "data"})
_WEB_SOURCE_TRAILING_JUNK = ".,);]>\"'"


def _normalize_web_source_url(value: str) -> str:
    text = (value or "").strip().strip(_WEB_SOURCE_TRAILING_JUNK)
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return text


def _iter_web_source_urls(obj: Any, *, allow_bare_strings: bool = False):
    if isinstance(obj, str):
        if allow_bare_strings:
            url = _normalize_web_source_url(obj)
            if url:
                yield url
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in _WEB_SOURCE_URL_KEYS and isinstance(value, str):
                url = _normalize_web_source_url(value)
                if url:
                    yield url
            elif key in _WEB_SOURCE_NEST_KEYS:
                yield from _iter_web_source_urls(
                    value,
                    allow_bare_strings=allow_bare_strings or key == "urls",
                )
        return
    if isinstance(obj, list):
        for item in obj:
            yield from _iter_web_source_urls(item, allow_bare_strings=allow_bare_strings)


def _parse_jsonish(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text[0] not in "{[":
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str) and part.strip():
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        return "\n".join(parts)
    for key in ("output", "result", "text"):
        raw = message.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw
    return ""


def _looks_like_web_payload(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    data = obj.get("data")
    if isinstance(data, dict) and isinstance(data.get("web"), list):
        return True
    results = obj.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict) and (
            isinstance(first.get("url"), str) or isinstance(first.get("href"), str)
        ):
            return True
    return False


def _assistant_tool_names_by_id(messages: list[Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("id") or "").strip()
            func = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(func.get("name") or call.get("name") or "").strip()
            if call_id and name:
                mapping[call_id] = name
    return mapping


_WEB_SOURCE_URL_STORE_CAP = 50


def collect_web_source_urls_from_messages(messages: list[Any] | None) -> list[str]:
    """Unique http(s) URLs from this turn's web_search / web_extract tool results."""
    if not isinstance(messages, list):
        return []
    last_user = -1
    for index, message in enumerate(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            last_user = index
    turn = messages[last_user + 1 :] if last_user >= 0 else messages
    id_to_name = _assistant_tool_names_by_id(messages)
    seen: set[str] = set()
    urls: list[str] = []

    def _add(obj: Any, *, allow_bare_strings: bool = False) -> None:
        for url in _iter_web_source_urls(obj, allow_bare_strings=allow_bare_strings):
            key = url.rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            urls.append(url)

    for message in turn:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        parsed = content if isinstance(content, (dict, list)) else _parse_jsonish(_message_text(message))
        role = message.get("role")
        name = str(message.get("name") or "").strip()
        if role == "tool":
            call_id = str(message.get("tool_call_id") or message.get("toolCallId") or "").strip()
            if not name and call_id:
                name = id_to_name.get(call_id, "")
            if name in _WEB_SOURCE_TOOLS or _looks_like_web_payload(parsed):
                _add(parsed)
            continue
        if _looks_like_web_payload(parsed):
            _add(parsed)
    return urls


def count_web_source_urls_from_messages(messages: list[Any] | None) -> int:
    """Unique http(s) URL count from this turn's web_search / web_extract tool results."""
    return len(collect_web_source_urls_from_messages(messages))


def attach_url_fetch_count(trace: dict[str, Any], messages: list[Any] | None) -> int:
    """Store this turn's web URL count and list on the live trace. Returns 0 when unused."""
    urls = collect_web_source_urls_from_messages(messages)
    count = len(urls)
    request = trace.setdefault("request", {})
    if not isinstance(request, dict):
        request = {}
        trace["request"] = request
    if count:
        stored = urls[:_WEB_SOURCE_URL_STORE_CAP]
        request["url_fetch_count"] = count
        request["url_fetch_urls"] = stored
        internet = trace.get("internet")
        if not isinstance(internet, dict):
            internet = {}
            trace["internet"] = internet
        internet["url_fetch_count"] = count
        internet["url_fetch_urls"] = list(stored)
    return count

