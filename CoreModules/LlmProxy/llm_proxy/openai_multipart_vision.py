"""OpenAI multimodal (text + image_url) helpers for Ollama /api/chat vision."""

from __future__ import annotations

import base64
import binascii
import contextlib
import ipaddress
import json
import os
import re
import socket
from typing import Any
from urllib.parse import urlparse

import requests

_DATA_IMAGE_INLINE_RE = re.compile(r"data:image/[a-z0-9.+-]+;base64,", re.IGNORECASE)
_DATA_URL_HEAD = re.compile(
    r"^data:(image/[a-zA-Z0-9.+-]+);base64,",
    re.IGNORECASE,
)

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
        with contextlib.suppress(Exception):
            r.close()


def sanitize_openai_text_part(text: str, *, max_chars: int = 80_000) -> str:
    """Cap plain-text length for proxy safety (inline data URLs are promoted upstream, not stripped here)."""
    s = (text or "").strip()
    if not s:
        return ""

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


def _promote_data_urls_in_plain_text(text: str) -> list[dict[str, Any]]:
    """
    Split ``text`` into OpenAI-style parts whenever a valid ``data:image/...;base64,...`` URL appears.

    Invalid or oversized blobs become a short ``text`` note; scanning advances to avoid tight loops.
    """
    out: list[dict[str, Any]] = []
    pos = 0
    images_kept = 0
    n = len(text)
    while pos < n:
        m = _DATA_IMAGE_INLINE_RE.search(text, pos)
        if m is None:
            tail = text[pos:]
            if tail.strip():
                out.append({"type": "text", "text": tail})
            break
        before = text[pos : m.start()]
        if before.strip():
            out.append({"type": "text", "text": before})
        k = m.end()
        while k < n and text[k] in " \t\n\r":
            k += 1
        b = k
        while b < n and text[b] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=":
            b += 1
        candidate_full = text[m.start() : b]
        payload, err = data_url_to_ollama_image_b64(candidate_full)
        if payload is None and b > m.end():
            for end_idx in range(b, m.end(), -1):
                trial = text[m.start() : end_idx]
                p2, _e2 = data_url_to_ollama_image_b64(trial)
                if p2 is not None:
                    candidate_full = trial
                    payload = p2
                    b = end_idx
                    err = None
                    break
        if payload is not None and images_kept < VISION_MAX_IMAGES_PER_MESSAGE:
            out.append({"type": "image_url", "image_url": {"url": candidate_full}})
            images_kept += 1
            pos = b
        else:
            note = _NOTE_TOO_MANY if images_kept >= VISION_MAX_IMAGES_PER_MESSAGE else err or _NOTE_INVALID
            out.append({"type": "text", "text": note})
            pos = b if b > m.end() else m.end()
    return out


def promote_inline_data_image_urls_in_content(content: Any) -> Any:
    """
    Rewrite string or multipart ``content`` so inline ``data:image/...;base64,...`` become ``image_url`` parts.

    Returns the original value when there is nothing to promote. String input that yields a single
    text-only part collapses back to a plain string for backward compatibility.
    """
    if isinstance(content, str):
        if not content or _DATA_IMAGE_INLINE_RE.search(content) is None:
            return content
        parts = _promote_data_urls_in_plain_text(content)
        if len(parts) == 1 and parts[0].get("type") == "text":
            return str(parts[0].get("text") or "")
        return parts
    if not isinstance(content, list):
        return content
    out: list[dict[str, Any]] = []
    for p in content:
        if not isinstance(p, dict):
            continue
        typ = p.get("type")
        image_url = _part_to_image_url(p)
        if image_url:
            out.append({"type": "image_url", "image_url": {"url": image_url}})
            continue
        if typ == "text" or (typ is None and isinstance(p.get("text"), str)):
            tx = str(p.get("text", ""))
            if not tx:
                continue
            if _DATA_IMAGE_INLINE_RE.search(tx) is None:
                out.append({"type": "text", "text": tx})
                continue
            out.extend(_promote_data_urls_in_plain_text(tx))
            continue
        try:
            dumped = json.dumps(p, ensure_ascii=False)
        except (TypeError, ValueError):
            dumped = str(p)
        out.append({"type": "text", "text": dumped})
    return out if out else content


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


def _media_type(part: dict[str, Any]) -> str:
    return str(part.get("mediaType") or part.get("mimeType") or part.get("mime") or "").strip().lower()


def _image_data_to_data_url(data: Any, media_type: str) -> str:
    s = str(data or "").strip()
    if not s:
        return ""
    if s.lower().startswith("data:image"):
        return s
    if s.lower().startswith("http://") or s.lower().startswith("https://"):
        return s
    if media_type.startswith("image/"):
        return f"data:{media_type};base64,{s}"
    return ""


def _part_to_image_url(part: dict[str, Any]) -> str:
    typ = part.get("type")
    if typ == "image_url":
        return _image_url_string(part)
    if typ == "image":
        media_type = _media_type(part)
        return _image_data_to_data_url(part.get("image") or part.get("data") or part.get("url"), media_type)
    if typ == "file":
        media_type = _media_type(part)
        if not media_type.startswith("image/"):
            return ""
        return _image_data_to_data_url(part.get("data") or part.get("url"), media_type)
    return ""


def collect_ollama_images_b64_from_parts(parts: list[Any]) -> list[str]:
    """Extract Ollama ``images`` entries from OpenAI-style parts (data URLs only)."""
    out: list[str] = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        url = _part_to_image_url(p)
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
        url = _part_to_image_url(p)
        if url:
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
    promoted = promote_inline_data_image_urls_in_content(content)
    if isinstance(promoted, list):
        text = openai_parts_to_flat_text(promoted)
        images = collect_ollama_images_b64_from_parts(promoted)
        msg: dict[str, Any] = {"role": "user", "content": sanitize_openai_text_part(text)}
        if images:
            msg["images"] = images
        return msg
    if isinstance(promoted, str):
        return {"role": "user", "content": sanitize_openai_text_part(promoted)}
    if content is None:
        return {"role": "user", "content": ""}
    try:
        dumped = json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        dumped = str(content)
    return {"role": "user", "content": sanitize_openai_text_part(dumped)}
