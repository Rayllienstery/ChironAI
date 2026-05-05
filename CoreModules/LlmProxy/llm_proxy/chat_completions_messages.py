"""Request message normalization, vision inlining, and OpenAI-shaped sanitization."""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

from infrastructure.ollama.openai_multipart_vision import (
    openai_parts_to_flat_text,
    promote_inline_data_image_urls_in_content,
    sanitize_openai_text_part,
    sanitize_proxy_content_parts,
    VISION_MAX_DECODED_BYTES,
)

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
