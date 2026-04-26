"""OpenAI multimodal (text + image_url) helpers for Ollama /api/chat vision."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import socket
import ipaddress
from urllib.parse import urlparse
from typing import Any

import requests

_DATA_IMAGE_INLINE_RE = re.compile(r"data:image/[a-z0-9.+-]+;base64,", re.IGNORECASE)
_DATA_URL_HEAD = re.compile(
    r"^data:(image/[a-zA-Z0-9.+-]+);base64,",
    re.IGNORECASE,
)

# When False, allow inline `data:image/...;base64,...` inside string-only content.
_STRIP_INLINE_DATA_URLS = str(os.getenv("LLM_PROXY_VISION_STRIP_INLINE_DATA_URLS", "1")).strip() not in {
    "0",
    "false",
    "no",
}

# When True, allow server-side fetching of external http(s) image URLs.
_FETCH_EXTERNAL_IMAGE_URLS = str(os.getenv("LLM_PROXY_VISION_FETCH_EXTERNAL_URLS", "0")).strip() in {
    "1",
    "true",
    "yes",
}

# Guardrails for external fetch.
_EXTERNAL_FETCH_TIMEOUT = (3.0, 10.0)  # (connect, read)
_EXTERNAL_FETCH_MAX_REDIRECTS = 3

# Ollama accepts large payloads; keep a sane server-side cap.
VISION_MAX_DECODED_BYTES = 20 * 1024 * 1024
VISION_MAX_IMAGES_PER_MESSAGE = 16

_NOTE_EXTERNAL = (
    "[Image: external URLs are not loaded by the proxy. Use a data:image/...;base64,... URL.]"
)
_NOTE_TOO_LARGE = "[Image omitted: data URL exceeds the configured size limit.]"
_NOTE_TOO_MANY = "[Image omitted: too many images in one message.]"
_NOTE_INVALID = "[Image omitted: invalid or unsupported image data URL.]"
_NOTE_FETCH_FAILED = "[Image omitted: failed to fetch external image URL.]"


def _url_looks_safe_for_fetch(url: str) -> bool:
    """
    Best-effort SSRF guard: block private/loopback/link-local/etc.
    This does not guarantee safety in all environments; keep behind an explicit flag.
    """
    u = (url or "").strip()
    if not u:
        return False
    p = urlparse(u)
    if p.scheme not in {"http", "https"}:
        return False
    host = (p.hostname or "").strip()
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except Exception:
        return False
    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0] if isinstance(sockaddr, tuple) and sockaddr else ""
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def http_image_url_to_data_url(url: str) -> tuple[str | None, str | None]:
    """
    Fetch an external http(s) image URL and convert to a data URL.
    Returns (data_url, note). Note is a user-safe error string.
    """
    if not _FETCH_EXTERNAL_IMAGE_URLS:
        return None, _NOTE_EXTERNAL
    if not _url_looks_safe_for_fetch(url):
        return None, _NOTE_FETCH_FAILED
    try:
        r = requests.get(
            url,
            timeout=_EXTERNAL_FETCH_TIMEOUT,
            stream=True,
            allow_redirects=True,
            headers={"User-Agent": "llm-proxy-vision-fetch/1.0"},
        )
    except Exception:
        return None, _NOTE_FETCH_FAILED
    try:
        # Reject too many redirects (requests follows automatically; we can still bound by history length).
        if len(getattr(r, "history", []) or []) > _EXTERNAL_FETCH_MAX_REDIRECTS:
            return None, _NOTE_FETCH_FAILED
        ct = str(r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not ct.startswith("image/"):
            return None, _NOTE_FETCH_FAILED
        buf = bytearray()
        for chunk in r.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) > VISION_MAX_DECODED_BYTES:
                return None, _NOTE_TOO_LARGE
        b64 = base64.b64encode(bytes(buf)).decode("ascii")
        return f"data:{ct};base64,{b64}", None
    finally:
        try:
            r.close()
        except Exception:
            pass


def sanitize_openai_text_part(text: str, *, max_chars: int = 80_000) -> str:
    """
    Same rules as LLM Proxy message sanitization: strip huge inline data URLs and cap length.
    """
    s = (text or "").strip()
    if not s:
        return ""

    if _STRIP_INLINE_DATA_URLS:
        m = _DATA_IMAGE_INLINE_RE.search(s)
        if m is not None:
            prefix = s[: m.start()].rstrip()
            note = (
                "[Image omitted: inline data:image;base64 payload was removed because it exceeds the model context. "
                "Please attach the image as a file/attachment or describe it in text.]"
            )
            s = (prefix + "\n\n" + note).strip() if prefix else note

    if len(s) > max_chars:
        s = s[:max_chars].rstrip() + "\n\n" + f"[Truncated: exceeded {max_chars} characters.]"
    return s


def data_url_to_ollama_image_b64(data_url: str) -> tuple[str | None, str | None]:
    """
    Validate a data:image/...;base64,... URL for Ollama.

    Returns (base64_payload_after_comma, error_note_or_none).
    On success the first element is suitable for Ollama's ``images`` array.
    """
    u = (data_url or "").strip()
    if not u.lower().startswith("data:image"):
        return None, None
    m = _DATA_URL_HEAD.match(u)
    if not m:
        return None, _NOTE_INVALID
    b64 = u[m.end() :].strip()
    if not b64:
        return None, _NOTE_INVALID
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return None, _NOTE_INVALID
    if len(raw) > VISION_MAX_DECODED_BYTES:
        return None, _NOTE_TOO_LARGE
    return b64, None


def openai_parts_to_flat_text(parts: list[Any]) -> str:
    """Join OpenAI ``type:text`` parts (single spaces), ignoring other types."""
    out_parts: list[str] = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text" and isinstance(p.get("text"), str):
            t = (p.get("text") or "").strip()
            if t:
                out_parts.append(t)
    return " ".join(out_parts).strip()


def _image_url_string(part: dict[str, Any]) -> str:
    iu = part.get("image_url")
    if isinstance(iu, str):
        return iu.strip()
    if isinstance(iu, dict):
        return str(iu.get("url") or "").strip()
    return ""


def collect_ollama_images_b64_from_parts(parts: list[Any]) -> list[str]:
    """Extract Ollama ``images`` entries from OpenAI-style parts (data URLs only)."""
    out: list[str] = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("type") != "image_url":
            continue
        url = _image_url_string(p)
        b64, _err = data_url_to_ollama_image_b64(url)
        if b64 is not None and len(out) < VISION_MAX_IMAGES_PER_MESSAGE:
            out.append(b64)
    return out


def sanitize_proxy_content_parts(parts: list[Any]) -> str | list[dict[str, Any]]:
    """
    Normalize multipart ``content`` for the proxy: keep valid data-URL images, replace others with text notes.

    Returns either a plain string (no retained images) or an OpenAI-style part list when at least one
    ``image_url`` is kept for downstream vision mapping.
    """
    kept_images = 0
    out: list[dict[str, Any]] = []

    for p in parts:
        if not isinstance(p, dict):
            continue
        typ = p.get("type")
        if typ == "text" or (typ is None and isinstance(p.get("text"), str)):
            st = sanitize_openai_text_part(str(p.get("text", "")))
            if st:
                out.append({"type": "text", "text": st})
            continue
        if typ == "image_url":
            url = _image_url_string(p)
            if not url:
                continue
            ul = url
            if ul.lower().startswith("data:image"):
                b64, err = data_url_to_ollama_image_b64(ul)
                if b64 is None:
                    note = err or _NOTE_INVALID
                    sn = sanitize_openai_text_part(note)
                    if sn:
                        out.append({"type": "text", "text": sn})
                    continue
                if kept_images >= VISION_MAX_IMAGES_PER_MESSAGE:
                    sn = sanitize_openai_text_part(_NOTE_TOO_MANY)
                    if sn:
                        out.append({"type": "text", "text": sn})
                    continue
                kept_images += 1
                out.append({"type": "image_url", "image_url": {"url": ul}})
                continue
            if ul.lower().startswith("http://") or ul.lower().startswith("https://"):
                fetched, note = http_image_url_to_data_url(ul)
                if fetched and fetched.lower().startswith("data:image"):
                    if kept_images >= VISION_MAX_IMAGES_PER_MESSAGE:
                        sn = sanitize_openai_text_part(_NOTE_TOO_MANY)
                        if sn:
                            out.append({"type": "text", "text": sn})
                        continue
                    kept_images += 1
                    out.append({"type": "image_url", "image_url": {"url": fetched}})
                    continue
                sn = sanitize_openai_text_part(note or _NOTE_EXTERNAL)
                if sn:
                    out.append({"type": "text", "text": sn})
                continue
            sn = sanitize_openai_text_part(_NOTE_INVALID)
            if sn:
                out.append({"type": "text", "text": sn})
            continue
        try:
            dumped = json.dumps(p, ensure_ascii=False)
        except (TypeError, ValueError):
            dumped = str(p)
        sn = sanitize_openai_text_part(f"[Non-text part omitted] {dumped}")
        if sn:
            out.append({"type": "text", "text": sn})

    if kept_images == 0:
        # Flatten retained text parts to a single string (same shape as legacy proxy messages).
        return openai_parts_to_flat_text(out)

    return out


def build_ollama_user_message_from_openai_content(content: Any) -> dict[str, Any]:
    """
    Map OpenAI ``user`` ``content`` (string or multipart list) to an Ollama /api/chat message dict.
    Adds ``images`` when multipart contains valid ``data:image`` URLs.
    """
    if isinstance(content, list):
        text = openai_parts_to_flat_text(content)
        images = collect_ollama_images_b64_from_parts(content)
        msg: dict[str, Any] = {"role": "user", "content": text}
        if images:
            msg["images"] = images
        return msg
    if isinstance(content, str):
        return {"role": "user", "content": sanitize_openai_text_part(content)}
    if content is None:
        return {"role": "user", "content": ""}
    try:
        dumped = json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        dumped = str(content)
    return {"role": "user", "content": sanitize_openai_text_part(dumped)}


def ollama_messages_drop_images(messages: list[Any]) -> list[dict[str, Any]]:
    """
    Shallow-copy ``messages`` and drop ``images`` on each turn.

    Some Ollama backends (especially cloud + tool calling) reject multimodal ``images`` in the same
    ``/api/chat`` request as ``tools``; the proxy still keeps full messages in the trace.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        mm = dict(m)
        mm.pop("images", None)
        out.append(mm)
    return out
