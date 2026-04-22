"""Map OpenAI Chat Completions tool protocol to Ollama /api/chat and back."""

from __future__ import annotations

import json
import uuid
from typing import Any

from infrastructure.ollama.openai_multipart_vision import build_ollama_user_message_from_openai_content


def _new_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:24]}"


def _sanitize_tool_name(raw: object, *, fallback: str = "tool") -> str:
    if isinstance(raw, str):
        name = raw.strip()
        if name:
            return name
    return fallback


def _message_tool_call_id(message: dict[str, Any]) -> str:
    for key in ("tool_call_id", "tool_callid", "call_id", "id"):
        value = message.get(key)
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
    return ""


_THOUGHT_SIGNATURE_SKIP_VALIDATOR = "skip_thought_signature_validator"


def _extract_thought_signature_from_tool_call(tool_call: dict[str, Any], fn: dict[str, Any]) -> str:
    candidates: list[Any] = []
    if isinstance(fn, dict):
        candidates.extend((fn.get("thought_signature"), fn.get("thoughtSignature")))
    candidates.extend((tool_call.get("thought_signature"), tool_call.get("thoughtSignature")))
    extra = tool_call.get("extra_content")
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


def arguments_to_ollama_object(raw: object | None) -> dict[str, Any]:
    """OpenAI uses function.arguments as JSON string; Ollama expects an object."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def arguments_to_openai_string(obj: object | None) -> str:
    """Serialize tool arguments for OpenAI-style function.arguments string."""
    if obj is None:
        return "{}"
    if isinstance(obj, str):
        return obj if obj.strip() else "{}"
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"


def _openai_message_content_to_text(content: object) -> str:
    """
    Flatten OpenAI/Chat-style message content for Ollama (string or content-parts array).

    Important: system/developer messages may use the same multipart list shape as user;
    using str(list) would produce useless Python repr and breaks model behavior.
    """
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict):
                typ = p.get("type")
                if typ == "text" or (typ is None and "text" in p):
                    parts.append(str(p.get("text", "")))
                    continue
                if typ == "image_url":
                    iu = p.get("image_url")
                    url = ""
                    if isinstance(iu, str):
                        url = iu.strip()
                    elif isinstance(iu, dict):
                        url = str(iu.get("url") or "").strip()
                    ul = url
                    if ul.lower().startswith("data:image"):
                        parts.append("[image: inline data URL omitted]")
                    elif ul.lower().startswith("http://") or ul.lower().startswith("https://"):
                        parts.append("[image: external URL omitted]")
                    elif ul:
                        parts.append("[image]")
                    continue
                try:
                    parts.append(json.dumps(p, ensure_ascii=False))
                except (TypeError, ValueError):
                    parts.append(str(p))
                continue
            if p is None:
                continue
            parts.append(str(p))
        return "\n".join(parts) if parts else ""
    if content is None:
        return ""
    if isinstance(content, dict):
        try:
            return json.dumps(content, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(content)
    return str(content)


def _user_content_to_text(content: object) -> str:
    """Deprecated name; use _openai_message_content_to_text."""
    return _openai_message_content_to_text(content)


def _build_tool_call_id_to_name(messages: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for c in tcs:
            if not isinstance(c, dict):
                continue
            call_id = _message_tool_call_id(c)
            fn = c.get("function") if isinstance(c.get("function"), dict) else {}
            name = _sanitize_tool_name(fn.get("name") if isinstance(fn, dict) else None)
            if call_id:
                out[call_id] = name
    return out


def openai_messages_to_ollama(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Convert OpenAI chat messages (including tool role and assistant tool_calls)
    to Ollama /api/chat message list.
    """
    tool_call_id_to_name = _build_tool_call_id_to_name(messages)
    ollama: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role in ("system", "developer"):
            ollama.append({"role": "system", "content": _openai_message_content_to_text(m.get("content"))})
            continue
        if role == "user":
            ollama.append(build_ollama_user_message_from_openai_content(m.get("content")))
            continue
        if role == "assistant":
            text = _openai_message_content_to_text(m.get("content"))
            tcs = m.get("tool_calls")
            if isinstance(tcs, list) and tcs:
                ollama_calls: list[dict[str, Any]] = []
                for idx, c in enumerate(tcs):
                    if not isinstance(c, dict):
                        continue
                    fn = c.get("function") if isinstance(c.get("function"), dict) else {}
                    name = _sanitize_tool_name(fn.get("name") if isinstance(fn, dict) else None)
                    call_id = _message_tool_call_id(c)
                    args_obj = arguments_to_ollama_object(fn.get("arguments") if isinstance(fn, dict) else None)
                    ollama_fn: dict[str, Any] = {"name": name, "arguments": args_obj}
                    if isinstance(fn, dict) and fn.get("index") is not None:
                        try:
                            ollama_fn["index"] = int(fn["index"])
                        except (TypeError, ValueError):
                            ollama_fn["index"] = idx
                    else:
                        ollama_fn["index"] = idx
                    thought_signature = _extract_thought_signature_from_tool_call(c, fn)
                    if not thought_signature:
                        # Google-documented fallback to keep Gemini function-call validation permissive
                        # when upstream adapters omit signatures.
                        thought_signature = _THOUGHT_SIGNATURE_SKIP_VALIDATOR
                    ollama_fn["thought_signature"] = thought_signature
                    ollama_call: dict[str, Any] = {"type": "function", "function": ollama_fn}
                    if call_id:
                        ollama_call["id"] = call_id
                        ollama_call["call_id"] = call_id
                    extra_content = c.get("extra_content")
                    if isinstance(extra_content, dict):
                        extra_out = dict(extra_content)
                    else:
                        extra_out = {}
                    google = extra_out.get("google")
                    if isinstance(google, dict):
                        google_out = dict(google)
                    else:
                        google_out = {}
                    google_out.setdefault("thought_signature", thought_signature)
                    extra_out["google"] = google_out
                    ollama_call["extra_content"] = extra_out
                    ollama_calls.append(ollama_call)
                out_msg: dict[str, Any] = {"role": "assistant", "content": text}
                if ollama_calls:
                    out_msg["tool_calls"] = ollama_calls
                if "signature" in m:
                    out_msg["signature"] = m["signature"]
                ollama.append(out_msg)
            else:
                plain_assistant: dict[str, Any] = {"role": "assistant", "content": text}
                if "signature" in m:
                    plain_assistant["signature"] = m["signature"]
                ollama.append(plain_assistant)
            continue
        if role == "tool":
            name = _sanitize_tool_name(m.get("name"), fallback="")
            if not name:
                name = _sanitize_tool_name(m.get("tool_name"), fallback="")
            if not name:
                tcid = _message_tool_call_id(m)
                if tcid:
                    name = _sanitize_tool_name(tool_call_id_to_name.get(tcid), fallback="tool")
                else:
                    name = "tool"
            raw_c = m.get("content")
            content = raw_c if isinstance(raw_c, str) else json.dumps(raw_c, ensure_ascii=False)
            # Keep both aliases for broader backend compatibility (e.g. Gemini adapters expect `name`).
            ollama.append({"role": "tool", "tool_name": name, "name": name, "content": content})
            continue
        if role == "function":
            name = m.get("name")
            if not isinstance(name, str) or not name:
                name = "function"
            raw_c = m.get("content")
            content = raw_c if isinstance(raw_c, str) else json.dumps(raw_c, ensure_ascii=False)
            ollama.append({"role": "tool", "tool_name": name, "name": name, "content": content})
            continue
        extra = _openai_message_content_to_text(m.get("content"))
        label = str(role) if role not in (None, "") else "unknown"
        ollama.append(
            {
                "role": "user",
                "content": f"[openai_message role={label}]\n{extra}" if extra else f"[openai_message role={label}]",
            }
        )
    return ollama


def openai_tool_choice_means_none(raw: Any) -> bool:
    """True when the client asked for no tools (OpenAI string or dict shape)."""
    if raw is None or raw == "":
        return False
    if isinstance(raw, str):
        return raw.strip().lower() == "none"
    if isinstance(raw, dict):
        return str(raw.get("type") or "").strip().lower() == "none"
    return False


def ollama_chat_tool_choice_payload_value(raw: Any) -> str | None:
    """
    Map OpenAI ``tool_choice`` to a value safe for Ollama ``POST /api/chat``.

    OpenAI allows object shapes (e.g. ``{"type": "auto"}``, function forcing). Ollama's native
    endpoint expects a small string enum or the field omitted; passing arbitrary dicts often
    yields **400 Bad Request**.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("", "auto"):
            return None
        if s == "none":
            return "none"
        if s == "required":
            return "required"
        return None
    if isinstance(raw, dict):
        return None
    return None


def ollama_tools_from_openai(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Return only Ollama-compatible function tools."""
    if not tools:
        return None
    out: list[dict[str, Any]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        ttype = str(t.get("type") or "").strip().lower()
        if ttype not in ("", "function"):
            continue
        fn = t.get("function") if isinstance(t.get("function"), dict) else {}
        if not isinstance(fn, dict):
            fn = {}
        fn_name = _sanitize_tool_name(fn.get("name"), fallback="")
        if not fn_name:
            fn_name = _sanitize_tool_name(t.get("name"), fallback="")
        if not fn_name:
            continue
        fn_out: dict[str, Any] = {"name": fn_name}
        params = fn.get("parameters")
        if isinstance(params, dict):
            fn_out["parameters"] = params
        elif isinstance(t.get("parameters"), dict):
            fn_out["parameters"] = t["parameters"]
        if isinstance(fn.get("description"), str) and fn.get("description").strip():
            fn_out["description"] = fn["description"].strip()
        elif isinstance(t.get("description"), str) and t.get("description").strip():
            fn_out["description"] = t["description"].strip()
        if isinstance(fn.get("strict"), bool):
            fn_out["strict"] = fn["strict"]
        elif isinstance(t.get("strict"), bool):
            fn_out["strict"] = t["strict"]
        out.append({"type": "function", "function": fn_out})
    return out or None


def ollama_message_to_openai_assistant(ollama_msg: dict[str, Any]) -> dict[str, Any]:
    """
    Build OpenAI `message` object from Ollama assistant `message` payload.
    Returns dict with keys: role, content (optional), tool_calls (optional).
    Merges Ollama ``thinking`` into ``content`` (single visible string; no ``reasoning_content``).
    """
    role = ollama_msg.get("role") or "assistant"
    content = ollama_msg.get("content")
    if content is not None and not isinstance(content, str):
        content = str(content)
    tcs = ollama_msg.get("tool_calls")
    openai_calls: list[dict[str, Any]] = []
    if isinstance(tcs, list):
        for c in tcs:
            if not isinstance(c, dict):
                continue
            fn = c.get("function") if isinstance(c.get("function"), dict) else {}
            name = str(fn.get("name") or "tool") if isinstance(fn, dict) else "tool"
            args_raw = fn.get("arguments") if isinstance(fn, dict) else None
            arg_str = arguments_to_openai_string(args_raw)
            fn_out: dict[str, Any] = {"name": name, "arguments": arg_str}
            thought_signature = _extract_thought_signature_from_tool_call(c, fn)
            if thought_signature:
                fn_out["thought_signature"] = thought_signature
            call_id = _message_tool_call_id(c) or _new_call_id()
            call_out: dict[str, Any] = {
                "id": call_id,
                "call_id": call_id,
                "type": "function",
                "function": fn_out,
            }
            extra_content = c.get("extra_content")
            if isinstance(extra_content, dict):
                extra_out = dict(extra_content)
            else:
                extra_out = {}
            if thought_signature:
                google = extra_out.get("google")
                if isinstance(google, dict):
                    google_out = dict(google)
                else:
                    google_out = {}
                google_out.setdefault("thought_signature", thought_signature)
                extra_out["google"] = google_out
            if extra_out:
                call_out["extra_content"] = extra_out
            openai_calls.append(call_out)
    thinking = ollama_msg.get("thinking")
    th = thinking.strip() if isinstance(thinking, str) else ""
    co = (content or "").strip() if content else ""
    if th and co:
        merged = f"{th}\n\n{co}"
    else:
        merged = co or th

    msg: dict[str, Any] = {"role": str(role)}
    if merged:
        msg["content"] = merged
    elif not openai_calls:
        msg["content"] = None
    else:
        msg["content"] = None
    if openai_calls:
        msg["tool_calls"] = openai_calls
    if "signature" in ollama_msg:
        msg["signature"] = ollama_msg["signature"]
    return msg


def openai_finish_reason_from_ollama(
    ollama_msg: dict[str, Any],
    ollama_done_reason: str | None = None,
) -> str:
    if isinstance(ollama_msg.get("tool_calls"), list) and ollama_msg.get("tool_calls"):
        return "tool_calls"
    dr = (
        (ollama_done_reason or "").strip().lower()
        if isinstance(ollama_done_reason, str)
        else ""
    )
    if dr == "length":
        return "length"
    return "stop"


__all__ = [
    "arguments_to_ollama_object",
    "arguments_to_openai_string",
    "ollama_chat_tool_choice_payload_value",
    "openai_finish_reason_from_ollama",
    "openai_messages_to_ollama",
    "openai_tool_choice_means_none",
    "ollama_message_to_openai_assistant",
    "ollama_tools_from_openai",
]
