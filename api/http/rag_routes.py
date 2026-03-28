"""
Flask routes for OpenAI-compatible RAG proxy.

Exposes /v1/models, /v1/chat/completions, /, /v1, /health.
Uses application.rag.use_cases with wired dependencies from application.container.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
import uuid
import hashlib
import base64
import shlex
from urllib.parse import unquote

from flask import Flask, Response, jsonify, request

# Ensure project root on path when running from api or WebUI.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# So that "from rag_service ..." works (rag_service package lives in modules/rag_service).
_MODULES_RAG = os.path.join(_ROOT, "modules", "rag_service")
if _MODULES_RAG not in sys.path:
    sys.path.insert(0, _MODULES_RAG)
# External docs RAG module (multi-collection, trigger keywords).
_MODULES_EXT_RAG = os.path.join(_ROOT, "modules", "external_docs_rag")
if _MODULES_EXT_RAG not in sys.path:
    sys.path.insert(0, _MODULES_EXT_RAG)

from application.rag.collection_freshness import check_collection_freshness
from application.rag.params import RAGDependencies, get_rag_answer_params
from application.rag.use_cases import build_rag_context, prepare_ollama_messages
from domain.entities.rag import RagContext, RagQuestionRequest
from infrastructure.database import get_settings_repository

try:
    from external_docs_rag.application.use_cases import (
        build_merged_rag_context,
        ingest_github_repo_markdown,
        resolve_rag_sources_for_request,
    )
    from external_docs_rag.config_loader import (
        load_external_sources,
        load_github_repos,
        load_rag_sources_config,
    )
    from external_docs_rag.infrastructure import (
        HttpFetchClient,
        QdrantChunkSink,
        QdrantRagSearchAdapter,
    )
    from external_docs_rag.infrastructure.github_discovery import get_latest_release_tag
    _EXTERNAL_DOCS_RAG_AVAILABLE = True
except ImportError:
    build_merged_rag_context = None  # type: ignore[assignment]
    resolve_rag_sources_for_request = None  # type: ignore[assignment]
    load_rag_sources_config = None  # type: ignore[assignment]
    load_external_sources = None  # type: ignore[assignment]
    load_github_repos = None  # type: ignore[assignment]
    ingest_github_repo_markdown = None  # type: ignore[assignment]
    HttpFetchClient = None  # type: ignore[assignment]
    QdrantChunkSink = None  # type: ignore[assignment]
    QdrantRagSearchAdapter = None  # type: ignore[assignment]
    get_latest_release_tag = None  # type: ignore[assignment]
    _EXTERNAL_DOCS_RAG_AVAILABLE = False

try:
    from config import (
        get_default_rag_top_k,
        get_framework_collection_ttl_days,
        get_proxy_rerank_enabled,
        get_qdrant_url,
    )
except ImportError:
    get_proxy_rerank_enabled = lambda: False  # type: ignore[assignment]
    get_qdrant_url = lambda: "http://localhost:6333"  # type: ignore[assignment]
    get_framework_collection_ttl_days = lambda: 90  # type: ignore[assignment]
    get_default_rag_top_k = lambda: 4  # type: ignore[assignment]
try:
    from rag_service.infrastructure.keyword_collections_sqlite import get_keyword_collections_repository
except ImportError:
    get_keyword_collections_repository = None  # type: ignore[assignment]


def _get_rag_required_keywords_from_module() -> list[str] | None:
    """Return flat list of enabled keywords from rag_service module, or None to use config default."""
    if get_keyword_collections_repository is None:
        return None
    try:
        repo = get_keyword_collections_repository()
        flat = repo.get_enabled_keywords_flat()
        return flat if flat else None
    except Exception:
        return None
from domain.services.prompt_builder import determine_reasoning_level, last_user_content
from infrastructure.logging.webui_error_logger import log_webui_error
from infrastructure.database import get_session_manager, get_logs_repository
from api.http.proxy_status import (
    set_proxy_status,
    set_latest_request_seconds,
    set_latest_request_total_tokens,
    set_latest_request_rag_steps,
    STATUS_IDLE,
    STATUS_RAG_SEARCH,
    STATUS_PREPARING_RESPONSE,
    STATUS_RESPONSE,
)
from api.http.proxy_trace import set_current_trace
import time

RAG_MODEL_ID = "rag-ollama"
_RAG_LOG = logging.getLogger("trag.rag")
_APPLY_EDIT_TOOL_NAME = "apply_file_edit"


def _log_rag_error(stage: str, error: Exception) -> None:
    """One-line console log: RAG stage=... | ErrorType: message."""
    _RAG_LOG.error("RAG stage=%s | %s: %s", stage, type(error).__name__, error)


def _workspace_root() -> Path:
    return Path(_ROOT).resolve()


def _resolve_workspace_path(file_path: str) -> Path:
    if not file_path or not str(file_path).strip():
        raise ValueError("file_path is required")
    root = _workspace_root()
    candidate = Path(file_path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("file_path points outside workspace") from exc
    return resolved


def _replace_text_range(original: str, range_data: dict[str, object], new_text: str) -> str:
    lines = original.splitlines(keepends=True)
    start_line = int(range_data.get("start_line") or 0)
    end_line = int(range_data.get("end_line") or 0)
    start_col = int(range_data.get("start_col") or 1)
    end_col = int(range_data.get("end_col") or 1)
    if start_line < 1 or end_line < 1 or start_line > end_line:
        raise ValueError("Invalid range: line indices")
    if start_line > len(lines) or end_line > len(lines):
        raise ValueError("Range out of bounds")
    start_line_text = lines[start_line - 1]
    end_line_text = lines[end_line - 1]
    if start_col < 1 or start_col > (len(start_line_text) + 1):
        raise ValueError("Invalid range: start_col")
    if end_col < 1 or end_col > (len(end_line_text) + 1):
        raise ValueError("Invalid range: end_col")
    if start_line == end_line and end_col < start_col:
        raise ValueError("Invalid range: end_col before start_col")

    prefix = "".join(lines[: start_line - 1]) + start_line_text[: start_col - 1]
    suffix = end_line_text[end_col - 1 :] + "".join(lines[end_line:])
    return f"{prefix}{new_text}{suffix}"


def _extract_edit_from_response(content: str) -> dict[str, object] | None:
    text = (content or "").strip()
    if not text:
        return None

    def _first_balanced_json_object(s: str) -> str | None:
        start = s.find("{")
        if start < 0:
            return None
        depth = 0
        in_str = False
        escaped = False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == "\"":
                    in_str = False
                continue
            if ch == "\"":
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
        return None

    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    payload = m.group(1) if m else None
    if payload is None:
        payload = _first_balanced_json_object(text)

    if payload is None:
        return None
    try:
        obj = json.loads(payload)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    # Batch-style payloads
    paths = obj.get("paths")
    if isinstance(paths, list) and paths:
        first = paths[0]
        if isinstance(first, dict):
            obj = {
                "path": first.get("path") or first.get("file_path"),
                "content": first.get("content") or "",
                "mode": obj.get("mode") or "create",
                "display_description": obj.get("display_description") or "",
            }
    file_path = obj.get("file_path") or obj.get("path")
    if not file_path:
        return None
    has_text = bool(
        obj.get("new_text") or obj.get("patch") or obj.get("replacement") or obj.get("content")
    )
    # Require actual code/text for any file edit payload. Even for create/overwrite,
    # an empty body typically means "no-op" in IDE clients.
    if not has_text:
        return None
    if "file_path" not in obj:
        obj["file_path"] = file_path
    if "new_text" not in obj:
        obj["new_text"] = obj.get("replacement") or obj.get("content") or ""
    return obj


def _extract_line_span_from_user_text(user_text: str) -> tuple[int, int] | None:
    m = re.search(r"\(\s*(\d+)\s*:\s*(\d+)\s*\)", user_text or "")
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if a < 1 or b < 1 or a > b:
        return None
    return (a, b)


def _strip_context_sections(text: str) -> str:
    """Remove client-injected context blocks so we can dedup and retry reliably."""
    s = (text or "")
    if not s:
        return ""
    # Common Zed/Cursor style: "<context> ... </context>" or "<context>\n...".
    s = re.sub(r"<context>[\s\S]*$", "", s, flags=re.IGNORECASE).strip()
    # Remove generic attachment boilerplate that can vary run-to-run.
    s = re.sub(
        r"The following items were attached by the user[\s\S]*$",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()
    # Collapse whitespace for stable comparisons.
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalized_user_signature(text: str) -> str:
    """Stable signature for deduping repeated user requests."""
    base = _strip_context_sections(text)
    if not base:
        return ""
    # Remove volatile line-span anchors like #L1:12 while keeping the path.
    base = re.sub(r"#L\\d+(?::\\d+)?", "", base, flags=re.IGNORECASE)
    base = re.sub(r"\\s+", " ", base).strip()
    return base.lower()


def _workspace_selection_snippet(user_query: str, max_chars: int = 12000) -> str:
    """Load current file lines for (start:end) in user_query to ground the model."""
    span = _extract_line_span_from_user_text(user_query or "")
    if not span:
        return ""
    raw_path = _extract_file_path_from_user_text(user_query or "")
    if not raw_path:
        return ""
    rel = _normalize_tool_path(raw_path)
    if rel:
        rel = _resolve_workspace_relative_path_hint(rel)
    if not rel:
        return ""
    root = _workspace_root()
    fp = root / rel
    try:
        if not fp.is_file():
            return ""
        text = fp.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines = text.splitlines()
    a, b = span
    if a < 1 or b < 1 or a > b or a > len(lines):
        return ""
    b_eff = min(b, len(lines))
    chunk = "\n".join(lines[a - 1 : b_eff])
    if len(chunk) > max_chars:
        chunk = chunk[:max_chars] + "\n... [truncated]"
    return (
        f"\n\n[proxy:current_file_excerpt] `{rel}` lines {a}-{b_eff} (1-based, from disk):\n```\n{chunk}\n```\n"
        "Apply the user instruction to THIS excerpt; your tool JSON must include the full new source for the "
        "edited region (non-empty `content` / `new_text` / `replacement`).\n"
    )


def _client_selection_snippet(user_query: str, max_chars: int = 12000) -> str:
    """
    Extract a selection excerpt embedded by the client (e.g. Zed <selections> blocks).
    This is used when the file is outside the workspace so we can't read from disk.
    """
    text = user_query or ""
    span = _extract_line_span_from_user_text(text)
    if not span:
        return ""
    raw_path = _extract_file_path_from_user_text(text or "")
    if not raw_path:
        return ""
    # Heuristic: capture the first fenced block after "<selections>".
    m = re.search(r"<selections>[\\s\\S]*?```(?:\\w+)?\\s*([\\s\\S]*?)```", text, flags=re.IGNORECASE)
    if not m:
        return ""
    chunk = (m.group(1) or "").strip()
    if not chunk:
        return ""
    if len(chunk) > max_chars:
        chunk = chunk[:max_chars] + "\n... [truncated]"
    a, b = span
    rel = _normalize_tool_path(raw_path) or raw_path
    return (
        f"\n\n[proxy:client_selection_excerpt] `{rel}` lines {a}-{b} (1-based, provided by client):\n```\n{chunk}\n```\n"
        "Apply the user instruction to THIS excerpt; your tool JSON must include the full new source for the "
        "edited region (non-empty `content` / `new_text` / `replacement`).\n"
    )


_CLIENT_FILES_FENCE_RE = re.compile(
    r"<files>[\s\S]*?```(?:\w+)?[^\n]*\n([\s\S]*?)```",
    flags=re.IGNORECASE,
)


def _client_files_excerpt_and_full_range(
    user_query: str,
) -> tuple[str | None, dict[str, object] | None]:
    """First fenced body inside <files> and a 1-based range covering all its lines, or (None, None)."""
    m = _CLIENT_FILES_FENCE_RE.search(user_query or "")
    if not m:
        return (None, None)
    excerpt = (m.group(1) or "").rstrip("\n")
    line_count = len(excerpt.splitlines()) if excerpt else 0
    if line_count <= 0:
        return (None, None)
    range_obj: dict[str, object] = {
        "start_line": 1,
        "start_col": 1,
        "end_line": int(line_count),
        "end_col": 1,
    }
    return (excerpt, range_obj)


def _client_files_snippet(user_query: str, max_chars: int = 12000) -> str:
    """
    Extract a full-file excerpt embedded by the client (e.g. Zed <files> blocks).
    Useful when the file is outside the workspace or has been clobbered by a bad tool call.
    """
    text = user_query or ""
    raw_path = _extract_file_path_from_user_text(text or "")
    if not raw_path:
        return ""
    excerpt, _fr = _client_files_excerpt_and_full_range(text)
    if not excerpt:
        return ""
    chunk = excerpt.strip()
    if not chunk:
        return ""
    if len(chunk) > max_chars:
        chunk = chunk[:max_chars] + "\n... [truncated]"
    rel = _normalize_tool_path(raw_path) or raw_path
    return (
        f"\n\n[proxy:client_file_excerpt] `{rel}` (provided by client):\n```\n{chunk}\n```\n"
        "Apply the user instruction to THIS file content; your tool JSON must include the full updated source "
        "(non-empty `content` / `new_text` / `replacement`).\n"
    )


_ADDITIVE_INTENT_MARKERS = (
    "add ",
    "insert ",
    "foreach",
    "for each",
    "also ",
    "append ",
    "include ",
    "добав",
    "встав",
    "для каждого",
    "ещё ",
    "еще ",
)
_SHRINK_OR_REPLACE_MARKERS = (
    "удали",
    "delete ",
    "remove ",
    "сожми",
    "shrink",
    "replace whole",
    "перепиши",
    "rewrite ",
    "replace entire",
    "очисти",
    "clear ",
)


def _ranges_equal_for_edit(a: dict[str, object], b: dict[str, object]) -> bool:
    for k in ("start_line", "end_line", "start_col", "end_col"):
        if a.get(k) != b.get(k):
            return False
    return True


def _effective_edit_range_for_partial_guard(
    user_query: str, edit_payload: dict[str, object]
) -> tuple[dict[str, object] | None, dict[str, object] | None, str | None]:
    """(effective_range, files_full_range, files_excerpt). files_* None when no <files> block."""
    files_excerpt, files_range = _client_files_excerpt_and_full_range(user_query or "")
    range_obj: dict[str, object] = {}
    pr = edit_payload.get("range")
    if isinstance(pr, dict) and pr:
        range_obj = dict(pr)
    if not range_obj:
        span = _extract_line_span_from_user_text(user_query or "")
        if span:
            a, b = span
            range_obj = {
                "start_line": int(a),
                "start_col": 1,
                "end_line": int(b),
                "end_col": 1,
            }
    if not range_obj and files_range:
        range_obj = dict(files_range)
    if not range_obj:
        return (None, files_range, files_excerpt)
    return (range_obj, files_range, files_excerpt)


def _payload_body_looks_partial_vs_files_excerpt(user_query: str, excerpt: str, body: str) -> bool:
    q = _strip_context_sections(user_query or "").lower()
    if any(m in q for m in _SHRINK_OR_REPLACE_MARKERS):
        return False
    if not any(m in q for m in _ADDITIVE_INTENT_MARKERS):
        return False
    ex_lines = [ln for ln in excerpt.splitlines() if ln.strip()]
    new_lines = [ln for ln in body.splitlines() if ln.strip()]
    if not ex_lines:
        return False
    if len(new_lines) >= len(ex_lines):
        return False
    first_ex = ex_lines[0].strip()
    if first_ex and first_ex in body:
        return False
    return True


def _needs_internal_full_file_retry(
    user_query: str,
    edit_payload: dict[str, object],
    selected_tool_name: str | None,
) -> bool:
    if not selected_tool_name or not _is_edit_like_tool_name(selected_tool_name):
        return False
    n = selected_tool_name.lower()
    if "replace" in n and "range" in n:
        return False
    eff, fr, excerpt = _effective_edit_range_for_partial_guard(user_query, edit_payload)
    if not excerpt or not fr or not eff:
        return False
    if not _ranges_equal_for_edit(eff, fr):
        return False
    body = _edit_payload_body_text(edit_payload)
    if not body.strip():
        return False
    return _payload_body_looks_partial_vs_files_excerpt(user_query, excerpt, body)


def _maybe_retry_edit_payload_full_file(
    chat_client: object,
    use_model: str,
    user_query: str,
    selected_tool_name: str | None,
    selected_tool: dict[str, object] | None,
    edit_payload: dict[str, object],
) -> tuple[dict[str, object], bool]:
    """If model returned a fragment for a full-<files> range edit, retry once inside the proxy."""
    if not selected_tool_name or not _needs_internal_full_file_retry(
        user_query, edit_payload, selected_tool_name
    ):
        return (edit_payload, False)
    tool_json_instruction = _build_tool_json_instruction(selected_tool_name, selected_tool)
    user_part = (user_query or "").strip()
    fix = (
        "\n\n[proxy:full_file_retry] The IDE attached the full current file in <files>. "
        "Your last answer only put a code fragment in new_text/content. "
        "Reply with ONE JSON object where new_text (or content) is the COMPLETE updated file: "
        "keep all lines that should remain and apply the user's edit—do not send only the new loop/block."
    )
    messages: list[dict[str, object]] = []
    if tool_json_instruction:
        messages.append({"role": "system", "content": tool_json_instruction})
    messages.append({"role": "user", "content": user_part + fix})
    try:
        raw = chat_client.chat(messages, use_model, stream=False, options=None)
        new_ep = _extract_edit_from_response(raw or "")
        if isinstance(new_ep, dict):
            return (new_ep, True)
    except Exception:
        pass
    return (edit_payload, False)


def _strict_retry_user_content(user_query: str, selected_tool_name: str | None) -> str:
    base = (user_query or "").strip()
    if not base:
        return base
    span = _extract_line_span_from_user_text(base)
    extra_parts: list[str] = [
        "\n\n[proxy:strict_tool_json] Return a single JSON object only. No markdown or commentary."
    ]
    if span:
        a, b = span
        if selected_tool_name and "replace" in selected_tool_name.lower() and "range" in selected_tool_name.lower():
            extra_parts.append(
                f"The user selection is lines {a}-{b} (1-based inclusive). "
                "Include workspace-relative `path` and non-empty `replacement`: the FULL multi-line text "
                "that replaces exactly that line range (e.g. the full `const tabs = [...]` block). "
                "Never omit `replacement`."
            )
        else:
            extra_parts.append(
                f"The user selection is lines {a}-{b} (1-based inclusive). "
                "Include non-empty `new_text` or `content` with the actual updated code for that region; "
                "never emit only metadata fields. `mode` must be edit, create, or overwrite (never empty)."
            )
    else:
        extra_parts.append(
            "Include non-empty `new_text`, `content`, or `replacement` (whichever the tool schema requires) "
            "with the actual code changes."
        )
    excerpt = _workspace_selection_snippet(base)
    if not excerpt:
        excerpt = _client_selection_snippet(base) or _client_files_snippet(base)
    return base + "".join(extra_parts) + excerpt


def _extract_file_path_from_user_text(user_text: str) -> str | None:
    if not user_text:
        return None
    # Prefer full file:// URIs from IDE links (works for macOS/Linux/Windows).
    m_uri3 = re.search(r"(file:///[^\s)#]+)", user_text)
    if m_uri3:
        return (m_uri3.group(1) or "").split("#", 1)[0]
    m_uri2 = re.search(r"(file://[^\s)#]+)", user_text)
    if m_uri2:
        return (m_uri2.group(1) or "").split("#", 1)[0]
    # Capture @label like [@App.jsx (283:293)] or [@App.jsx](file:///...).
    m3 = re.search(r"\[@([^\]\r\n]+?)\s*\(\d+\s*:\s*\d+\)\]", user_text)
    if m3:
        return m3.group(1).strip()
    m3b = re.search(r"\[@([^\]\r\n]+?)\]\(", user_text)
    if m3b:
        return m3b.group(1).strip()
    # Plain Windows path in text.
    m4 = re.search(r"([A-Za-z]:/[^\s)#]+)", user_text)
    if m4:
        return m4.group(1).strip()
    # Plain filename token (e.g. "App.jsx") as last resort.
    m5 = re.search(r"\b([A-Za-z0-9_.-]+\.(?:jsx|tsx|js|ts|py|md|txt|json|yaml|yml))\b", user_text)
    if m5:
        return m5.group(1).strip()
    return None


def _resolve_workspace_relative_path_hint(path_hint: str) -> str:
    hint = (path_hint or "").strip().replace("\\", "/").lstrip("./")
    if not hint:
        return ""
    root = _workspace_root()
    try:
        # Already a valid relative path?
        if "/" in hint and (root / hint).exists():
            return hint
        # Basename case (e.g. App.jsx)
        candidates = [
            hint,
            f"modules/webui_frontend/src/{hint}",
            f"src/{hint}",
            f"WebUI/{hint}",
        ]
        for rel in candidates:
            try:
                if rel and (root / rel).exists():
                    return rel.replace("\\", "/").lstrip("./")
            except Exception:
                continue
    except Exception:
        return hint
    return hint


def _normalize_tool_path(file_path: str) -> str:
    raw = (file_path or "").strip()
    if not raw:
        return ""
    normalized = raw.replace("\\", "/")
    if normalized.startswith("file:///"):
        normalized = normalized[8:]
    root = _workspace_root()
    try:
        candidate = Path(normalized)
        if candidate.is_absolute():
            resolved = candidate.resolve()
            try:
                rel = resolved.relative_to(root)
                return rel.as_posix()
            except ValueError:
                return normalized
    except Exception:
        return normalized
    return normalized.lstrip("./")


def _tool_path_from_uri_or_path(raw_path: str) -> str:
    """
    Convert file:// URIs into IDE tool-friendly local paths.
    - file:///C:/x -> C:/x
    - file:///Users/x -> /Users/x
    Non-URI inputs are returned as-is (trimmed).
    """
    s = (raw_path or "").strip()
    if not s:
        return ""
    if not s.startswith("file://"):
        return s
    path_part = unquote(s[7:])
    # Windows URI form: /C:/...
    if re.match(r"^/[A-Za-z]:/", path_part):
        return path_part[1:]
    # POSIX URI form: /Users/...
    if path_part.startswith("/"):
        return path_part
    return path_part


def _is_create_intent(user_query: str) -> bool:
    q = (user_query or "").lower()
    if not q:
        return False
    markers = ["create file", "generate file", "new file", "создай файл", "сгенерируй файл", "создать файл"]
    return any(m in q for m in markers)


def _extract_tool_name(tool_obj: object) -> str | None:
    if not isinstance(tool_obj, dict):
        return None
    fn = tool_obj.get("function")
    if not isinstance(fn, dict):
        return None
    name = fn.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _select_edit_tool_name(tools: list[object], user_query: str = "") -> str | None:
    names = [n for n in (_extract_tool_name(t) for t in tools) if n]
    if not names:
        return None
    q = user_query or ""
    span = _extract_line_span_from_user_text(q) if q else None
    if q and span is not None:
        for n in names:
            low = n.lower()
            if "replace" in low and "range" in low:
                return n
    # Prefer a write-capable apply/edit tool when available.
    if _APPLY_EDIT_TOOL_NAME in names:
        t = _get_tool_by_name(tools, _APPLY_EDIT_TOOL_NAME)
        if _tool_schema_accepts_content(t):
            return _APPLY_EDIT_TOOL_NAME
    # Prefer write-capable edit_file
    for n in names:
        if n.lower() == "edit_file":
            t = _get_tool_by_name(tools, n)
            if _tool_schema_accepts_content(t):
                return n
    # Prefer save_file only when it can carry content (avoid paths-only variants).
    for n in names:
        if n.lower() == "save_file":
            t = _get_tool_by_name(tools, n)
            if _tool_schema_accepts_content(t):
                return n
    # Fall back to replace/range tools (even if not first in list).
    for n in names:
        low = n.lower()
        if "replace" in low and "range" in low:
            return n
    # Final fallbacks: any edit-like tool name; schema may be incomplete but client might accept extra args.
    for n in names:
        low = n.lower()
        if "file" in low and ("edit" in low or "patch" in low or "replace" in low or "range" in low):
            return n
    for n in names:
        low = n.lower()
        if "edit" in low or "patch" in low or "replace" in low:
            return n
    return None


def _tool_schema_accepts_content(tool: dict[str, object] | None) -> bool:
    """
    Return True when tool schema can carry new file text.

    Supported patterns:
    - top-level string fields: content/new_text/replacement/text/new_content/patch
    - batch write: paths is array of objects with {path, content}-like fields

    Not supported:
    - paths as array of strings only (no place to carry text)
    """
    if not isinstance(tool, dict):
        return False
    fn = tool.get("function")
    if not isinstance(fn, dict):
        return False
    tool_name = fn.get("name") if isinstance(fn.get("name"), str) else ""
    params = fn.get("parameters")
    if not isinstance(params, dict):
        return False
    props = params.get("properties")
    if not isinstance(props, dict):
        props = {}
    required = params.get("required")
    req = required if isinstance(required, list) else []
    req_set = {str(x) for x in req if isinstance(x, str)}

    # Some IDEs (including Zed in certain configurations) provide very loose schemas like:
    #   parameters: { "type": "object" }
    # but still accept `content`/`new_text` at runtime. Treat these as write-capable based on name.
    if not props and not req_set:
        if _is_edit_like_tool_name(tool_name) and "terminal" not in (tool_name or "").lower():
            return True

    text_keys = ("content", "new_text", "replacement", "text", "new_content", "patch")
    if any(k in props or k in req_set for k in text_keys):
        return True

    paths_def = props.get("paths")
    if not isinstance(paths_def, dict):
        # Zed frequently provides partial schemas (e.g. edit_file without content field),
        # while still accepting content/new_text at runtime. For edit-like tools, prefer
        # attempting a tool call over hard-failing here.
        if _is_edit_like_tool_name(tool_name) and "terminal" not in (tool_name or "").lower():
            return True
        return False
    items = paths_def.get("items")
    # If schema doesn't specify item type, assume object items (common in loose schemas).
    if items is None:
        return True
    # If items are strings, we can only pass paths, not content.
    if isinstance(items, dict) and (items.get("type") == "string" or items.get("type") == "String"):
        return False
    # items object with content field
    if isinstance(items, dict):
        item_props = items.get("properties")
        if isinstance(item_props, dict):
            if any(k in item_props for k in ("content", "new_text", "text", "replacement", "new_content", "patch")):
                return True
        item_req = items.get("required")
        if isinstance(item_req, list):
            if any(str(x) in ("content", "new_text", "text", "replacement", "new_content", "patch") for x in item_req):
                return True
    return False


def _tool_result_looks_like_unintended_deletion(tool_text: str) -> bool:
    """
    Heuristic: detect tool results that appear to delete content without adding replacements.
    This commonly happens when a client tool was invoked with empty edit body.
    """
    t = (tool_text or "").strip()
    if not t:
        return False
    low = t.lower()
    if "```diff" not in low:
        return False
    # If a diff hunk indicates the new file has 0 lines where it previously had >0, treat as failure.
    if re.search(r"@@\\s+-\\d+,\\d+\\s+\\+\\d+,0\\s+@@", t):
        return True
    # If there are removed lines but no added lines in the diff body.
    if re.search(r"^-[^\\n]", t, flags=re.MULTILINE) and not re.search(r"^\\+[^\\n]", t, flags=re.MULTILINE):
        return True
    return False


_TOOL_RESULT_FAILURE_MARKERS_STRICT = (
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


def _collect_tool_result_contents_in_order(messages: list[object]) -> list[str]:
    out: list[str] = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") != "tool":
            continue
        out.append(
            str(
                m.get("content")
                or m.get("output")
                or m.get("result")
                or m.get("text")
                or ""
            )
        )
    return out


def _tool_content_indicates_successful_edit(tool_text: str) -> bool:
    """
    True when one tool_result looks like the IDE applied a real edit.

    Used so a trailing 'No edits were made.' after an earlier successful diff does not
    trip the cross-request noop counter (Zed sometimes emits an extra no-op round).
    """
    t = (tool_text or "").strip()
    if len(t) < 10:
        return False
    low = t.lower()
    if "no edits were made" in low:
        return False
    if any(x in low for x in _TOOL_RESULT_FAILURE_MARKERS_STRICT):
        return False
    if low.startswith("no edits") and len(t) < 160:
        return False
    if _tool_result_looks_like_unintended_deletion(tool_text):
        return False
    if "completed" in low or "successfully" in low:
        return True
    if "```" in t:
        for block in re.findall(r"```(?:[^\n`]*)\n([\s\S]*?)```", t, flags=re.IGNORECASE):
            if len((block or "").strip()) > 6:
                return True
    if "diff" in low and re.search(r"^\+[^\n]", t, flags=re.MULTILINE):
        return True
    return False


def _prior_tool_messages_include_successful_edit(messages: list[object]) -> bool:
    """Any tool_result before the last one in the transcript looks like a successful edit."""
    contents = _collect_tool_result_contents_in_order(messages)
    if len(contents) < 2:
        return False
    for c in contents[:-1]:
        if _tool_content_indicates_successful_edit(c):
            return True
    return False


def _get_tool_by_name(tools: list[object], name: str | None) -> dict[str, object] | None:
    if not name:
        return None
    for t in tools:
        if not isinstance(t, dict):
            continue
        if _extract_tool_name(t) == name:
            return t
    return None


def _select_terminal_tool_name(tools: list[object]) -> str | None:
    names = [n for n in (_extract_tool_name(t) for t in tools) if n]
    if not names:
        return None
    for n in names:
        if n.lower() == "terminal":
            return n
    for n in names:
        if "terminal" in n.lower():
            return n
    return None


def _terminal_write_file_command(abs_path: str, content: str) -> str:
    """
    Return a shell-agnostic command to write UTF-8 content to abs_path.

    Zed's `terminal` tool may run in bash (WSL) or PowerShell; generating a pure
    PowerShell script causes syntax errors in bash. Using Python keeps the
    command portable across shells.
    """
    b64 = base64.b64encode((content or "").encode("utf-8")).decode("ascii")
    # Important: keep python snippet free of single quotes to avoid bash quote-breaking.
    # Also avoid backslash-unicode escapes by using a JSON-escaped string literal.
    # Use forward slashes to avoid layers that "eat" backslashes (JSON -> shell -> python),
    # and to avoid Python's \U unicode-escape pitfalls on Windows-style paths.
    path_for_py = (abs_path or "").replace("\\", "/")
    path_lit = json.dumps(path_for_py)
    b64_lit = json.dumps(b64)
    # Use write_bytes to avoid newline normalization differences across shells.
    py = (
        "import base64, pathlib;"
        f"p=pathlib.Path({path_lit});"
        f"b={b64_lit};"
        "p.write_bytes(base64.b64decode(b))"
    )
    return f"python -c {shlex.quote(py)}"


def _build_terminal_tool_arguments(
    tools: list[object],
    terminal_tool_name: str,
    *,
    abs_path: str,
    content: str,
) -> dict[str, object]:
    t = _get_tool_by_name(tools, terminal_tool_name)
    fn = t.get("function") if isinstance(t, dict) else None
    params = fn.get("parameters") if isinstance(fn, dict) else None
    props = params.get("properties") if isinstance(params, dict) else None
    required = params.get("required") if isinstance(params, dict) else None
    prop_keys = set(str(k) for k in props.keys()) if isinstance(props, dict) else set()
    req_keys = set(str(x) for x in required if isinstance(x, str)) if isinstance(required, list) else set()
    keys = req_keys or prop_keys or {"command"}
    cmd = _terminal_write_file_command(abs_path, content)
    args: dict[str, object] = {}
    # Common field names across clients.
    if "command" in keys:
        args["command"] = cmd
    elif "cmd" in keys:
        args["cmd"] = cmd
    elif "script" in keys:
        args["script"] = cmd
    else:
        # Best effort.
        args["command"] = cmd
    # Zed terminal tool commonly requires `cd`.
    if "cd" in keys:
        args["cd"] = str(Path(abs_path).parent)
    if "cwd" in keys:
        args["cwd"] = str(Path(abs_path).parent)
    if "working_directory" in keys:
        args["working_directory"] = str(Path(abs_path).parent)
    return args


def _default_tool_keys(selected_tool_name: str) -> set[str]:
    n = (selected_tool_name or "").lower()
    if n == "save_file":
        return {"path", "content", "mode", "display_description"}
    if "replace" in n and "range" in n:
        return {"path", "replacement"}
    if "edit" in n and "file" in n:
        return {"path", "mode", "display_description", "content"}
    return {"file_path", "range", "new_text"}


def _coerce_zed_tool_mode(raw: object) -> str:
    s = str(raw).strip().lower() if raw is not None else ""
    if s in {"edit", "create", "overwrite"}:
        return s
    if s in {"w", "write"}:
        return "create"
    if s in {"fw"}:
        return "overwrite"
    if s in {"patch", "replace"}:
        return "edit"
    return "edit"


# Models sometimes emit junk placeholder lines inside replacements; strip before Zed applies the edit.
_EDIT_JUNK_LINE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*//\s*removed\s*$", re.I),
    re.compile(r"^\s*//\s*delete[ds]?\s*$", re.I),
    re.compile(r"^\s*//\s*placeholder\s*$", re.I),
    re.compile(r"^\s*#\s*removed\s*$", re.I),
    re.compile(r"^\s*//\s*\.\.\.\s*$"),
)


# Cache recent successful edits to suppress repeated client retries (e.g. Zed agent loops).
# Keyed by (user_signature, normalized_path). TTL is short to avoid masking real new intents.
_RECENT_SUCCESS_TTL_S = 45
_recent_success: dict[tuple[str, str], float] = {}
_RECENT_NOOP_TTL_S = 120
_recent_noop: dict[tuple[str, str], tuple[int, float]] = {}


def _now_s() -> float:
    return time.time()


def _prune_recent_success(now_s: float) -> None:
    if not _recent_success:
        return
    cutoff = now_s - _RECENT_SUCCESS_TTL_S
    stale = [k for k, ts in _recent_success.items() if ts < cutoff]
    for k in stale:
        _recent_success.pop(k, None)


def _prune_recent_noop(now_s: float) -> None:
    if not _recent_noop:
        return
    cutoff = now_s - _RECENT_NOOP_TTL_S
    stale = [k for k, (_, ts) in _recent_noop.items() if ts < cutoff]
    for k in stale:
        _recent_noop.pop(k, None)


def _compact_display_description(user_query: str, limit: int = 180) -> str:
    """
    Build a concise description for tool cards by stripping context/attachment blocks.
    """
    s = _strip_context_sections(user_query or "")
    if not s:
        return ""
    # Remove markdown file-link wrappers while preserving intent text.
    s = re.sub(r"\[@([^\]]+)\]\([^)]+\)", r"@\1", s)
    # Remove inline line anchors like (1:3) to keep description short.
    s = re.sub(r"\(\s*\d+\s*:\s*\d+\s*\)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _normalized_path_for_cache(user_query: str) -> str:
    p = _extract_file_path_from_user_text(user_query or "") or ""
    p = _normalize_tool_path(p) if p else ""
    return p.lower()


def _strip_placeholder_edit_lines(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        if any(r.match(line) for r in _EDIT_JUNK_LINE_RES):
            continue
        out.append(line)
    return "".join(out)


def _edit_payload_body_text(edit_payload: dict[str, object]) -> str:
    t = str(
        edit_payload.get("new_text")
        or edit_payload.get("content")
        or edit_payload.get("replacement")
        or ""
    )
    return _strip_placeholder_edit_lines(t)


def _is_edit_like_tool_name(name: str) -> bool:
    n = (name or "").lower()
    return any(x in n for x in ("edit", "replace", "write", "patch", "apply", "save"))


def _tool_args_have_substantive_body(tool_name: str, args: dict[str, object]) -> bool:
    """Edit-like tools must carry non-empty replacement/content; avoid empty Zed preview cards."""
    if not _is_edit_like_tool_name(tool_name):
        return True
    body_keys = ("replacement", "new_text", "content", "text", "new_content")
    present = [k for k in body_keys if k in args]
    # Some tools (notably `save_file`) carry content inside `paths`.
    paths = args.get("paths")
    if isinstance(paths, list):
        for item in paths:
            if isinstance(item, dict):
                c = item.get("content")
                if isinstance(c, str) and c.strip():
                    return True
    # If the tool arguments contain no editable body fields at all (and no paths content), treat as non-substantive.
    # Some clients accept extra keys even if schema omits them; we inject `content`/`new_text`
    # when we have real edits. If they're still missing, it's a no-op.
    if not present:
        return False
    for k in present:
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return True
    return False


_POST_TOOL_SUCCESS_SYSTEM = (
    "The latest message is a tool result and it did not report a failure. "
    "Reply with a short plain-text confirmation only. Do not output JSON, do not call file-edit tools again, "
    "and do not propose another patch for the same change unless the user asked for more."
)


def _sync_edit_file_duplicate_body_fields(args: dict[str, object]) -> None:
    """Mirror non-empty body across content/new_text/replacement for Zed-style edit tools."""
    t = ""
    if isinstance(args.get("content"), str) and str(args.get("content") or "").strip():
        t = str(args.get("content"))
    elif isinstance(args.get("new_text"), str) and str(args.get("new_text") or "").strip():
        t = str(args.get("new_text"))
    elif isinstance(args.get("replacement"), str) and str(args.get("replacement") or "").strip():
        t = str(args.get("replacement"))
    if not t:
        return
    if not isinstance(args.get("content"), str) or not str(args.get("content") or "").strip():
        args["content"] = t
    if not isinstance(args.get("new_text"), str) or not str(args.get("new_text") or "").strip():
        args["new_text"] = t
    if not isinstance(args.get("replacement"), str) or not str(args.get("replacement") or "").strip():
        args["replacement"] = t


def _build_tool_arguments(
    *,
    selected_tool_name: str,
    selected_tool: dict[str, object] | None,
    edit_payload: dict[str, object],
    user_query: str,
) -> dict[str, object]:
    user_path = _extract_file_path_from_user_text(user_query or "")
    payload_raw_path = str(edit_payload.get("file_path") or edit_payload.get("path") or "")
    normalized_payload_path = _normalize_tool_path(payload_raw_path) if payload_raw_path else ""
    file_path = normalized_payload_path
    # IDE-independent mode: if the user provided a file URI or absolute path, preserve it verbatim
    # so the client IDE applies the edit on its own machine.
    if isinstance(user_path, str) and user_path:
        up = user_path.strip()
        if up.startswith("file://") or re.match(r"^[A-Za-z]:/", up) or up.startswith("/"):
            file_path = _tool_path_from_uri_or_path(up)
            normalized_payload_path = file_path
    if user_path and file_path:
        try:
            root = _workspace_root()
            if not (root / file_path).exists():
                normalized_user_path = _normalize_tool_path(user_path)
                if normalized_user_path and (root / normalized_user_path).exists():
                    file_path = normalized_user_path
        except Exception:
            pass
    if user_path and not file_path:
        up2 = user_path.strip()
        if up2.startswith("file://") or re.match(r"^[A-Za-z]:/", up2) or up2.startswith("/"):
            file_path = _tool_path_from_uri_or_path(up2)
        else:
            file_path = _normalize_tool_path(user_path)
    # If the model returned a relative hint (e.g. Desktop/test.swift) but the user provided
    # an absolute file:///C:/... path, prefer the user's absolute path (even if outside workspace).
    if (
        user_path
        and file_path
        and not file_path.startswith("file://")
        and not re.match(r"^[A-Za-z]:/", file_path)
        and not file_path.startswith("/")
    ):
        normalized_user_path = _normalize_tool_path(user_path)
        if re.match(r"^[A-Za-z]:/", normalized_user_path) or normalized_user_path.startswith("/"):
            file_path = normalized_user_path
    if file_path and "/" not in file_path:
        file_path = _resolve_workspace_relative_path_hint(file_path)
    # Final guard: keep client-machine path semantics, but convert file:// URI to tool-local path.
    if isinstance(user_path, str) and user_path.strip().startswith("file://"):
        file_path = _tool_path_from_uri_or_path(user_path.strip())
    range_obj = edit_payload.get("range") if isinstance(edit_payload.get("range"), dict) else {}
    # If model omitted range but user explicitly selected lines, prefer range edit over full overwrite.
    if not range_obj:
        span = _extract_line_span_from_user_text(user_query or "")
        if span:
            a, b = span
            range_obj = {
                "start_line": int(a),
                "start_col": 1,
                "end_line": int(b),
                "end_col": 1,
            }
    # If no explicit selection range, but client attached full file content (<files> block),
    # derive a safe full-file range to avoid destructive overwrite behavior.
    has_client_file_excerpt = False
    if not range_obj:
        _ex_files, _range_files = _client_files_excerpt_and_full_range(user_query or "")
        if _ex_files and _range_files:
            has_client_file_excerpt = True
            range_obj = dict(_range_files)
    new_text = str(edit_payload.get("new_text") or "")
    desc = _compact_display_description(user_query or "")
    if not desc:
        desc = f"Apply requested edit via {selected_tool_name}"
    display_description = desc[:180]

    raw_mode = (
        edit_payload.get("mode")
        or edit_payload.get("operation")
        or edit_payload.get("variant")
    )
    mode_value = (
        _coerce_zed_tool_mode(raw_mode)
        if raw_mode not in (None, "")
        else ("create" if _is_create_intent(user_query) else "edit")
    )
    has_range = bool(range_obj)
    tool_name_l = (selected_tool_name or "").lower()
    # Zed may treat `edit_file` without `range` as a no-op unless we switch to full-file modes.
    # When model asks for `mode=edit` but provides no `range`, prefer `overwrite` (existing file)
    # or `create` (missing file) to ensure Swift/Desktop files get written.
    if mode_value == "edit" and not has_range and (
        "edit_file" in tool_name_l or "apply_file_edit" in tool_name_l
    ):
        # If we derived a safe range from client file excerpt, keep mode=edit.
        if has_client_file_excerpt:
            mode_value = "edit"
        else:
            try:
                fp_for_exists = file_path
                if isinstance(fp_for_exists, str) and fp_for_exists.startswith("file:///"):
                    fp_for_exists = fp_for_exists[8:]
                p = Path(fp_for_exists)
                exists = p.exists() if p.is_absolute() else (_workspace_root() / fp_for_exists).exists()
            except Exception:
                exists = False
            mode_value = "overwrite" if exists else "create"

    canonical_values: dict[str, object] = {
        "file_path": file_path,
        "path": file_path,
        "target_file": file_path,
        "new_text": new_text,
        "replacement": new_text,
        "text": new_text,
        "content": new_text,
        "new_content": new_text,
        "range": range_obj,
        "line_range": range_obj,
        "location": range_obj,
        "start_line": range_obj.get("start_line"),
        "end_line": range_obj.get("end_line"),
        "start_col": range_obj.get("start_col"),
        "end_col": range_obj.get("end_col"),
        "display_description": display_description,
        "mode": mode_value,
        "operation": mode_value,
        "variant": mode_value,
    }

    # If tool schema provides required keys, ensure they are present to avoid Zed-side rejection.
    properties: dict[str, object] = {}
    required: list[str] = []
    try:
        fn = selected_tool.get("function") if isinstance(selected_tool, dict) else None
        params = fn.get("parameters") if isinstance(fn, dict) else None
        if isinstance(params, dict) and isinstance(params.get("properties"), dict):
            properties = params.get("properties")  # type: ignore[assignment]
        if isinstance(params, dict) and isinstance(params.get("required"), list):
            required = [str(x) for x in params.get("required") if isinstance(x, str)]
    except Exception:
        required = []

    # Strict native mode: only schema keys (+ required keys) are emitted.
    keys_to_emit: set[str] = set(required)
    keys_to_emit.update(str(k) for k in properties.keys())
    if not keys_to_emit:
        keys_to_emit = set(_default_tool_keys(selected_tool_name))

    # Special handling for save-file batch payload (`paths`).
    # Some clients require tool input like:
    #   paths=[{"path": "...", "content": "..."}]
    # rather than a single `path`.
    if "paths" in keys_to_emit:
        paths_items_type = ""
        try:
            pdef = properties.get("paths") if isinstance(properties, dict) else None
            if isinstance(pdef, dict):
                items = pdef.get("items")
                if isinstance(items, dict):
                    t = items.get("type")
                    if isinstance(t, str):
                        paths_items_type = t.strip().lower()
        except Exception:
            paths_items_type = ""
        payload_paths = edit_payload.get("paths")
        if isinstance(payload_paths, list):
            if paths_items_type == "string":
                normalized_path_strings: list[str] = []
                for p in payload_paths:
                    if isinstance(p, dict):
                        p_path_raw = p.get("path") or p.get("file_path") or ""
                        p_path = _normalize_tool_path(str(p_path_raw)) if p_path_raw else ""
                        if p_path:
                            normalized_path_strings.append(p_path)
                    elif isinstance(p, str):
                        p_path = _normalize_tool_path(p) if p else ""
                        if p_path:
                            normalized_path_strings.append(p_path)
                canonical_values["paths"] = normalized_path_strings
            else:
                normalized_paths: list[dict[str, object]] = []
                for p in payload_paths:
                    if isinstance(p, dict):
                        p_path_raw = p.get("path") or p.get("file_path") or ""
                        p_content_raw = (
                            p.get("content")
                            or p.get("new_text")
                            or p.get("text")
                            or new_text
                        )
                        p_path = _normalize_tool_path(str(p_path_raw)) if p_path_raw else ""
                        p_content = str(p_content_raw) if p_content_raw is not None else ""
                        normalized_paths.append({"path": p_path, "content": p_content})
                    elif isinstance(p, str):
                        normalized_paths.append(
                            {"path": _normalize_tool_path(p) if p else "", "content": new_text}
                        )
                canonical_values["paths"] = normalized_paths
        elif file_path:
            if paths_items_type == "string":
                canonical_values["paths"] = [file_path]
            else:
                canonical_values["paths"] = [{"path": file_path, "content": new_text}]

    args: dict[str, object] = {}
    for key in keys_to_emit:
        if key in canonical_values and canonical_values[key] not in (None, ""):
            args[key] = canonical_values[key]
        elif key in edit_payload:
            # Passthrough: preserve client/model-provided fields that aren't derived
            # by canonical_values (helps with schema variations).
            val = edit_payload.get(key)
            if val not in (None, ""):
                if key in ("path", "file_path", "target_file") and not isinstance(val, str):
                    args[key] = str(val)
                else:
                    args[key] = val

    # Guarantee required fields are present, with conservative defaults.
    for key in required:
        if key in args and args.get(key) not in (None, ""):
            continue
        if key in canonical_values:
            args[key] = canonical_values[key]
        elif key in edit_payload and edit_payload.get(key) not in (None, ""):
            args[key] = edit_payload.get(key)  # type: ignore[assignment]
        elif key == "display_description":
            args[key] = display_description
        else:
            args[key] = [] if key == "paths" else ""

    # Zed rejects empty string for enum `mode` (edit/create/overwrite).
    for k in ("mode", "operation", "variant"):
        if k not in args:
            continue
        v = args.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            args[k] = "edit"
        else:
            args[k] = _coerce_zed_tool_mode(v)

    for _k in ("replacement", "new_text", "content", "text", "new_content"):
        if _k in args and isinstance(args[_k], str):
            args[_k] = _strip_placeholder_edit_lines(args[_k])

    # If schema-key filtering dropped body fields, but model produced valid edit text,
    # inject a best-effort text field so IDE tools can still apply the edit.
    if _is_edit_like_tool_name(selected_tool_name) and not _tool_args_have_substantive_body(
        selected_tool_name, args
    ):
        fallback_text = str(
            edit_payload.get("new_text")
            or edit_payload.get("content")
            or edit_payload.get("replacement")
            or ""
        )
        if fallback_text.strip():
            n = (selected_tool_name or "").lower()
            if "replace" in n and "range" in n:
                args["replacement"] = fallback_text
            elif "new_text" in keys_to_emit:
                args["new_text"] = fallback_text
            elif "content" in keys_to_emit:
                args["content"] = fallback_text
            else:
                # Loose schemas often still accept `content`.
                args["content"] = fallback_text

    # Compatibility: some clients omit `range` from schema but still require it for mode=edit.
    # If we have a known range (from model or user selection), always include it for edit_file-like tools.
    if _is_edit_like_tool_name(selected_tool_name):
        n = (selected_tool_name or "").lower()
        if ("edit_file" in n or "apply_file_edit" in n) and isinstance(range_obj, dict) and range_obj:
            if not isinstance(args.get("range"), dict) or not args.get("range"):
                args["range"] = range_obj
            if "start_line" in range_obj and args.get("start_line") in (None, "", 0):
                args["start_line"] = range_obj.get("start_line")
            if "end_line" in range_obj and args.get("end_line") in (None, "", 0):
                args["end_line"] = range_obj.get("end_line")
            if "start_col" in range_obj and args.get("start_col") in (None, "", 0):
                args["start_col"] = range_obj.get("start_col")
            if "end_col" in range_obj and args.get("end_col") in (None, "", 0):
                args["end_col"] = range_obj.get("end_col")

    # Compatibility: many edit_file implementations accept either `content` or `new_text`.
    # Send both when we have text to avoid client-side empty-overwrite behavior.
    if _is_edit_like_tool_name(selected_tool_name):
        n = (selected_tool_name or "").lower()
        if "edit_file" in n or "apply_file_edit" in n:
            _sync_edit_file_duplicate_body_fields(args)

    # Drop empty body strings so clients do not prefer an empty field over a filled one.
    if _is_edit_like_tool_name(selected_tool_name):
        for bk in ("replacement", "new_text", "content", "text", "new_content"):
            if bk in args and isinstance(args[bk], str) and not str(args[bk]).strip():
                del args[bk]
        n = (selected_tool_name or "").lower()
        if "edit_file" in n or "apply_file_edit" in n:
            _sync_edit_file_duplicate_body_fields(args)

    return args


def _build_tool_json_instruction(
    selected_tool_name: str | None,
    selected_tool: dict[str, object] | None,
) -> str:
    if not selected_tool_name:
        return ""
    fn: dict[str, object] = {}
    if isinstance(selected_tool, dict):
        maybe_fn = selected_tool.get("function")
        if isinstance(maybe_fn, dict):
            fn = maybe_fn  # type: ignore[assignment]
    params = fn.get("parameters") if isinstance(fn, dict) else {}
    required = (
        params.get("required")
        if isinstance(params, dict) and isinstance(params.get("required"), list)
        else []
    )
    properties = (
        params.get("properties")
        if isinstance(params, dict) and isinstance(params.get("properties"), dict)
        else {}
    )
    prop_names = [str(k) for k in properties.keys()]
    req_names = [str(x) for x in required if isinstance(x, str)]
    fields = req_names if req_names else prop_names
    if not fields:
        fields = sorted(_default_tool_keys(selected_tool_name))
    n = (selected_tool_name or "").lower()
    tail = ""
    if "replace" in n and "range" in n:
        tail = (
            " Required: non-empty `replacement` with the full multi-line text that replaces the user’s selected "
            "line range (not a description)."
        )
    elif "edit" in n and "file" in n:
        tail = (
            " Required for `edit` mode: non-empty `content` or `new_text` with the actual source code to apply "
            "(not just path/description/mode)."
        )
    return (
        "Tool-call mode is enabled. "
        f"Return ONLY a single valid JSON object for tool `{selected_tool_name}` with fields from tool schema: {fields}. "
        "Do not return markdown, code fences, comments, or explanations. "
        "Use workspace-relative path in `path`/`file_path` when applicable. "
        "If the schema includes `mode`, it must be exactly one of: edit, create, overwrite (never empty). "
        "Do not emit placeholder lines such as `// removed` or `// ...` in `content`/`replacement`; output only real source lines."
        f"{tail}"
    )


def create_app(
    webui_dir: str | None = None,
    system_prefix: str | None = None,
    system_suffix: str | None = None,
) -> Flask:
    """
    Create Flask app with RAG routes.
    webui_dir: directory containing last_collection.txt (e.g. WebUI).
    system_prefix/suffix: optional overrides for RAG system prompt; if None use config (same as rag_client).
    """
    app = Flask(__name__)
    params, deps = get_rag_answer_params(webui_dir=webui_dir)
    prefix = system_prefix if system_prefix is not None else params.system_prefix
    suffix = system_suffix if system_suffix is not None else params.system_suffix
    context_chunk_chars = params.context_chunk_chars
    context_total_chars = params.context_total_chars
    confidence_threshold = params.confidence_threshold
    ollama_model = params.model_name
    log_preview = params.log_preview_chars
    rag_repo = deps.rag_repo
    embed_provider = deps.embed_provider
    rerank_client = deps.rerank_client
    chat_client = deps.chat_client

    @app.route("/")
    def index() -> Response:
        """Redirect root to WebUI."""
        return Response(
            '<!DOCTYPE html><html><head><meta http-equiv="refresh" '
            'content="0; url=/webui"></head><body>'
            '<p>Redirecting to <a href="/webui">/webui</a>...</p>'
            "</body></html>",
            status=302,
            headers={"Location": "/webui"},
            mimetype="text/html; charset=utf-8",
        )

    @app.route("/v1", methods=["GET"])
    def v1_root() -> Response:
        return jsonify({"object": "api", "version": "v1"})

    @app.route("/health", methods=["GET"])
    def health() -> Response:
        return jsonify({"status": "ok"})

    @app.route("/v1/models", methods=["GET"])
    def list_models() -> Response:
        return jsonify({
            "object": "list",
            "data": [{"id": RAG_MODEL_ID, "object": "model", "created": 0, "owned_by": "local"}],
        })

    @app.route("/v1/chat/completions", methods=["POST"])
    def chat_completions() -> Response | tuple[Response, int]:
        start_time = time.time()
        user_query = ""
        rag_context_data = None
        response_content = ""
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
        set_current_trace(trace)
        
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "parse_body"})
            _log_rag_error("parse_body", e)
            return jsonify({"error": "Invalid JSON"}), 400
        messages = body.get("messages") or []
        if not messages:
            return jsonify({"error": "messages is required"}), 400
        stream = body.get("stream", False)
        requested_model = body.get("model") or RAG_MODEL_ID
        tools = body.get("tools") if isinstance(body.get("tools"), list) else []
        tool_choice = body.get("tool_choice")
        tool_choice_effective = tool_choice if tool_choice not in (None, "") else "auto"
        tool_choice_overridden_for_edit_intent = False
        explicit_reasoning = body.get("reasoning_level") or body.get("reasoning")
        include_rag_metadata = body.get("include_rag_metadata", False)
        force_rag = bool(body.get("force_rag"))
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
        _prev_user_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            mi = messages[i]
            if not isinstance(mi, dict):
                continue
            r = mi.get("role")
            if _last_tool_idx < 0 and r == "tool":
                _last_tool_idx = i
            if r == "user":
                if _last_user_idx < 0:
                    _last_user_idx = i
                elif _prev_user_idx < 0:
                    _prev_user_idx = i
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
        # Zed may send a trailing "No edits were made." after an earlier successful apply; treat as done.
        # Last message may be `user` (checkpoint) while `_ltl` still reflects the latest tool in the transcript.
        _trailing_noop_after_prior_success = (
            has_tool_result
            and "no edits were made" in _ltl
            and _prior_tool_messages_include_successful_edit(messages)
        )
        if not post_tool_success_turn and _trailing_noop_after_prior_success:
            if _last_role == "tool" and (_last_user_idx < 0 or _last_user_idx < _last_tool_idx):
                post_tool_success_turn = True
            elif (
                _last_role == "user"
                and _last_tool_idx >= 0
                and _last_user_idx >= 0
                and _last_user_idx > _last_tool_idx
            ):
                post_tool_success_turn = True
        # Some clients re-send the same user instruction after a successful tool result.
        # If we already saw a successful tool result after the previous occurrence of the same user text,
        # suppress re-entering tool mode to avoid infinite "no-op" tool recursion.
        duplicate_user_after_success = False
        try:
            if _last_user_idx >= 0 and _prev_user_idx >= 0:
                last_user_text = last_user_content([messages[_last_user_idx]])  # type: ignore[arg-type]
                prev_user_text = last_user_content([messages[_prev_user_idx]])  # type: ignore[arg-type]
                last_sig = _normalized_user_signature(last_user_text)
                prev_sig = _normalized_user_signature(prev_user_text)
                if last_sig and prev_sig and last_sig == prev_sig:
                    # Look for any tool result between prev_user and last_user.
                    for j in range(_prev_user_idx + 1, _last_user_idx):
                        mj = messages[j]
                        if isinstance(mj, dict) and mj.get("role") == "tool":
                            c = str(mj.get("content") or mj.get("output") or mj.get("result") or "")
                            if c and ("clean" in c.lower() or "ok" in c.lower() or "success" in c.lower()):
                                duplicate_user_after_success = True
                                break
        except Exception:
            duplicate_user_after_success = False

        # Update recent-success cache when we see a successful tool result.
        try:
            if has_tool_result and not tool_result_indicates_failure and last_tool_content:
                # Attribute success to the user message that PRECEDES the last tool result,
                # not necessarily the last user message in the entire list (clients may append a new user turn).
                tool_idx = _last_tool_idx if _last_tool_idx >= 0 else -1
                user_for_tool = ""
                if tool_idx > 0:
                    for j in range(tool_idx - 1, -1, -1):
                        mj = messages[j]
                        if isinstance(mj, dict) and mj.get("role") == "user":
                            c = mj.get("content")
                            if isinstance(c, str):
                                user_for_tool = c
                            elif isinstance(c, list):
                                user_for_tool = " ".join(
                                    p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"
                                )
                            break
                sig = _normalized_user_signature(user_for_tool)
                p = _normalized_path_for_cache(user_for_tool)
                if sig and p and any(x in _ltl for x in ("clean", "ok", "success", "completed")):
                    now_s = _now_s()
                    _prune_recent_success(now_s)
                    _recent_success[(sig, p)] = now_s
        except Exception:
            pass

        proxy_settings: dict[str, object] = {}
        proxy_model_setting = ""
        try:
            _settings_repo_chat = get_settings_repository()
            proxy_model_setting = (_settings_repo_chat.get_app_setting("proxy_model") or "").strip()
            _ps_json = _settings_repo_chat.get_app_setting("proxy_settings")
            if _ps_json:
                proxy_settings = json.loads(_ps_json)
        except Exception:
            pass
        if not proxy_model_setting and proxy_settings.get("model"):
            proxy_model_setting = str(proxy_settings.get("model") or "").strip()

        fetch_web_knowledge_raw = body.get("fetch_web_knowledge")
        if fetch_web_knowledge_raw is None:
            fetch_web_knowledge = bool(proxy_settings.get("fetch_web_knowledge", False))
        else:
            fetch_web_knowledge = bool(fetch_web_knowledge_raw)

        try:
            from config.rag_prompts import get_rag_system_prompt as _get_rag_prompt, rag_prompt_file_exists
        except ImportError:
            _get_rag_prompt = None  # type: ignore[assignment,misc]
            rag_prompt_file_exists = lambda _n: False  # type: ignore[assignment,misc]

        proxy_prompt_name_required: str | None = None
        proxy_ollama_for_logical_id: str | None = None
        if system_prefix is None:
            if _get_rag_prompt is None:
                return jsonify({"error": "RAG prompt module unavailable"}), 500
            _pn = str(proxy_settings.get("prompt_name") or "").strip()
            if not _pn or not rag_prompt_file_exists(_pn):
                return jsonify(
                    {
                        "error": (
                            "LLM Proxy is not configured: choose a valid Prompt template in WebUI "
                            "(LLM Proxy → Model Settings). The file prompts/<name>.md must exist."
                        ),
                        "detail": f"prompt_name={_pn!r}" if _pn else "prompt_name is empty",
                    }
                ), 400
            proxy_prompt_name_required = _pn
            if requested_model == "rag-ollama" or requested_model == RAG_MODEL_ID:
                if not proxy_model_setting or proxy_model_setting in ("rag-ollama", RAG_MODEL_ID):
                    return jsonify(
                        {
                            "error": (
                                "LLM Proxy is not configured: choose a concrete Ollama model in WebUI "
                                "(LLM Proxy → Model Settings), not rag-ollama."
                            ),
                        }
                    ), 400
                proxy_ollama_for_logical_id = proxy_model_setting

        set_proxy_status(STATUS_RAG_SEARCH)
        last_user = last_user_content(messages)
        user_query = last_user  # Store for logging
        # Track repeated "No edits were made." failures for the same request signature/path.
        noop_retry_blocked = False
        try:
            now_s = _now_s()
            _prune_recent_noop(now_s)
            if "no edits were made" in _ltl:
                sig = _normalized_user_signature(user_query or "")
                p = _normalized_path_for_cache(user_query or "")
                if sig and p:
                    key = (sig, p)
                    # Trailing no-op after an earlier successful edit in the same transcript
                    # must not advance the noop counter (avoids false 'repeatedly' blocks).
                    if _prior_tool_messages_include_successful_edit(messages):
                        _recent_noop.pop(key, None)
                    else:
                        prev_count, _prev_ts = _recent_noop.get(key, (0, 0.0))
                        new_count = prev_count + 1
                        _recent_noop[key] = (new_count, now_s)
                        # Allow one retry with improved payload, then stop recursion.
                        if new_count >= 2:
                            noop_retry_blocked = True
            elif has_tool_result and not tool_result_indicates_failure:
                # Successful tool result clears recent noop counter for this signature/path.
                sig = _normalized_user_signature(user_query or "")
                p = _normalized_path_for_cache(user_query or "")
                if sig and p:
                    _recent_noop.pop((sig, p), None)
        except Exception:
            noop_retry_blocked = False
        selected_edit_tool_name = _select_edit_tool_name(tools, user_query)
        selected_edit_tool = _get_tool_by_name(tools, selected_edit_tool_name) if selected_edit_tool_name else None
        # Cross-request recursion guard: if the same user intent+path was just successfully applied,
        # suppress tool mode to avoid repeated empty/no-op tool calls from client retries.
        try:
            now_s = _now_s()
            _prune_recent_success(now_s)
            sig = _normalized_user_signature(user_query or "")
            p = _normalized_path_for_cache(user_query or "")
            if sig and p and (sig, p) in _recent_success:
                if now_s - _recent_success[(sig, p)] < _RECENT_SUCCESS_TTL_S:
                    post_tool_success_turn = True
        except Exception:
            pass
        # Safety: never use a non-write-capable file tool for overwrite/create. If the selected tool
        # can't carry content, we will later fall back to terminal-based write.
        selected_tool_write_capable = _tool_schema_accepts_content(selected_edit_tool)
        # If the client omitted `tools` entirely but referenced a file, assume an IDE-side `edit_file`
        # tool exists (Zed supports it) and allow emitting tool_calls anyway.
        if (not tools) and (tool_choice_effective != "none"):
            user_text = user_query or last_user or ""
            if _extract_file_path_from_user_text(user_text):
                selected_edit_tool_name = "edit_file"
                selected_edit_tool = None
                selected_tool_write_capable = True
        if duplicate_user_after_success:
            # Treat as already completed; respond text-only and do not emit tool_calls.
            post_tool_success_turn = True
        if tools and tool_choice_effective == "none" and selected_edit_tool_name:
            path_hint = (_extract_file_path_from_user_text(user_query or "") or "").lower()
            q_low = (user_query or "").lower()
            swift_intent = (
                path_hint.endswith(".swift")
                or "uiviewcontroller" in q_low
                or "swiftui" in q_low
                or "import uikit" in q_low
            )
            if swift_intent:
                tool_choice_effective = "auto"
                tool_choice_overridden_for_edit_intent = True
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
        if requested_model == "rag-ollama" or requested_model == RAG_MODEL_ID:
            effective_ollama_model = proxy_ollama_for_logical_id or ollama_model
        else:
            effective_ollama_model = requested_model
        reasoning_level = determine_reasoning_level(
            last_user, context_length, effective_ollama_model, explicit_reasoning
        )

        actual_model = (
            effective_ollama_model
            if requested_model == "rag-ollama" or requested_model == RAG_MODEL_ID
            else requested_model
        )

        trace["request"] = {
            "requested_model": requested_model,
            "actual_model": actual_model,
            "stream": bool(stream),
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
            "tool_choice_overridden_for_edit_intent": bool(
                tool_choice_overridden_for_edit_intent
            ),
            "has_tool_result": bool(has_tool_result),
            "tool_result_indicates_failure": bool(tool_result_indicates_failure),
            "post_tool_success_turn": bool(post_tool_success_turn),
            "tool_result_last_content_preview": (last_tool_content[:240] if last_tool_content else ""),
            "duplicate_user_after_success": bool(duplicate_user_after_success),
            "recent_success_cache_hit": bool(
                _normalized_user_signature(user_query or "")
                and _normalized_path_for_cache(user_query or "")
                and (_normalized_user_signature(user_query or ""), _normalized_path_for_cache(user_query or ""))
                in _recent_success
            ),
            "force_rag": bool(force_rag),
            "fetch_web_knowledge": bool(fetch_web_knowledge),
            "reasoning_level": explicit_reasoning or reasoning_level,
            "user_query_preview": (user_query or "")[:500],
        }

        if noop_retry_blocked:
            msg = (
                "Edit tool reported 'No edits were made' repeatedly for the same selection. "
                "Please expand the selected range or provide full file context (<files>) and retry once."
            )
            trace["response"] = {
                "content_preview": msg[:log_preview],
                "content_length_chars": len(msg),
                "tool_calls_count": 0,
            }
            set_current_trace(trace)
            if stream:
                def generate_sse_noop_block():
                    oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': actual_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': actual_model, 'choices': [{'index': 0, 'delta': {'content': msg}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': actual_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                    yield "data: [DONE]\n\n"
                return Response(
                    generate_sse_noop_block(),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
            return jsonify(
                {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                    "object": "chat.completion",
                    "created": 0,
                    "model": actual_model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": msg},
                            "finish_reason": "stop",
                        }
                    ],
                }
            )

        # IDE-independent mode: do not fail fast solely on schema checks.
        # Some clients expose incomplete tool schemas but still accept write payloads at runtime.

        # Optional project_context: frameworks list -> fresh collection names for RAG filter, and needs_refresh for background index
        project_context = body.get("project_context")
        project_fresh_collection_names: set[str] | None = None
        needs_refresh: list[tuple[str, str]] = []  # (framework_id_lower, collection_name); also filled from resolved sources below
        if (
            fetch_web_knowledge
            and isinstance(project_context, dict)
            and _EXTERNAL_DOCS_RAG_AVAILABLE
            and load_rag_sources_config
        ):
            frameworks = project_context.get("frameworks") or []
            if frameworks:
                rag_sources_config = load_rag_sources_config()
                # Map framework name (e.g. "Alamofire") -> collection_name from config
                name_to_collection: dict[str, str] = {}
                for cfg in rag_sources_config:
                    for kw in (cfg.trigger_keywords or []):
                        name_to_collection[(kw or "").strip().lower()] = cfg.collection_name
                    if (cfg.external_source_id or "").strip():
                        name_to_collection[(cfg.external_source_id or "").strip().lower()] = cfg.collection_name
                ttl_days = get_framework_collection_ttl_days()
                settings_repo = None
                try:
                    settings_repo = get_settings_repository()
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
                    if check_collection_freshness(meta, ttl_days) == "fresh":
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
                settings_repo = get_settings_repository()
                request_collection = (settings_repo.get_app_setting("rag_collection") or "").strip() or None
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
        if request_collection:
            req_params, req_deps = get_rag_answer_params(
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
            actual_model = (
                effective_ollama_model
                if requested_model == "rag-ollama" or requested_model == RAG_MODEL_ID
                else requested_model
            )
            trace["request"]["actual_model"] = actual_model
            trace["request"]["collection_name"] = request_collection
            trace["request"]["collection_source"] = collection_source
        else:
            trace["request"]["collection_source"] = "default"

        if proxy_ollama_for_logical_id:
            effective_ollama_model = proxy_ollama_for_logical_id
        actual_model = (
            effective_ollama_model
            if requested_model == "rag-ollama" or requested_model == RAG_MODEL_ID
            else requested_model
        )
        trace["request"]["actual_model"] = actual_model

        # Proxy: do not read settings from DB; rerank is configurable via proxy_rerank_enabled.
        effective_rerank_client = (
            effective_base_rerank_client if get_proxy_rerank_enabled() else None
        )
        rag_keywords = _get_rag_required_keywords_from_module()

        # Skip embed/search/rerank when the client is doing a local selection-based edit (typical Zed flow).
        # Model Tester feels faster largely because use_rag=false avoids this entire retrieval stack.
        explicit_skip_rag = bool(body.get("skip_rag"))
        local_tool_edit_fast_path = (
            bool(tools)
            and bool(selected_edit_tool_name)
            and tool_choice_effective != "none"
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
        skip_rag_retrieval = explicit_skip_rag or local_tool_edit_fast_path
        trace["request"]["skip_rag_retrieval"] = bool(skip_rag_retrieval)

        # Build RAG context: multi-collection (external_docs_rag) when triggered, else single collection
        rag_ctx_for_log = None
        rag_timings: dict[str, float] = {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0}
        background_refresh_started = False
        trace["internet"] = {"background_refresh_started": False}
        try:
            if skip_rag_retrieval:
                rag_ctx_for_log = RagContext(context_text="", chunks_info=[], max_score=0.0)
                trace["rag"]["retrieval_skipped"] = True
            else:
                trace["rag"]["retrieval_skipped"] = False
            if not skip_rag_retrieval:
                use_merged = False
                if (
                    fetch_web_knowledge
                    and not request_collection
                    and _EXTERNAL_DOCS_RAG_AVAILABLE
                    and load_rag_sources_config
                    and resolve_rag_sources_for_request
                    and build_merged_rag_context
                    and QdrantRagSearchAdapter is not None
                ):
                    rag_sources_config = load_rag_sources_config()
                    body_rag_sources = body.get("rag_sources")
                    if isinstance(body_rag_sources, list):
                        body_rag_sources = [str(x) for x in body_rag_sources]
                    else:
                        body_rag_sources = None
                    resolved = resolve_rag_sources_for_request(last_user, messages, body_rag_sources, rag_sources_config)
                    # Use merged path whenever we have any resolved source: enables generic discovery
                    # (GitHub fetch for any framework name in the question) plus configured on-demand and RAG.
                    if len(resolved) >= 1:
                        use_merged = True
                        # Trigger full crawl for resolved sources that are missing or stale when repo is on GitHub
                        try:
                            _settings_repo = get_settings_repository()
                            _ttl_days = get_framework_collection_ttl_days()
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
                                if check_collection_freshness(meta, _ttl_days) != "fresh":
                                    fid = (cfg.external_source_id or cfg.collection_name or "").strip().lower() or cfg.collection_name.lower()
                                    resolved_needs_refresh.append((fid, cfg.collection_name))
                        work_list = list(needs_refresh)
                        for (fid, coll) in resolved_needs_refresh:
                            if coll not in [c for _, c in work_list]:
                                work_list.append((fid, coll))
                        if work_list and load_github_repos and ingest_github_repo_markdown and HttpFetchClient and QdrantChunkSink and get_latest_release_tag:
                            coll_to_framework_id = {}
                            for cfg in rag_sources_config:
                                fid = (cfg.external_source_id or cfg.collection_name or "").strip().lower()
                                if fid:
                                    coll_to_framework_id[cfg.collection_name] = fid
                            github_repos_list = load_github_repos()
                            by_framework_id = {(e.get("framework_id") or "").lower(): e for e in github_repos_list if e.get("framework_id")}

                            def _run_refresh(work: list) -> None:
                                try:
                                    qdrant_url = get_qdrant_url()
                                    fetch_client = HttpFetchClient()
                                    chunk_sink = QdrantChunkSink(base_url=qdrant_url)
                                    repo = get_settings_repository()
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
                                            tag = get_latest_release_tag(f"{owner}/{repo_name}")
                                            if tag:
                                                ref = tag
                                            else:
                                                ref = "main"
                                        ingest_github_repo_markdown(
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
                            qdrant_url = get_qdrant_url()
                        except Exception:
                            qdrant_url = "http://localhost:6333"
                        rag_search_adapter = QdrantRagSearchAdapter(base_url=qdrant_url)
                        fetch_client = HttpFetchClient() if HttpFetchClient is not None else None
                        external_sources_list = load_external_sources() if load_external_sources else []
                        merged_ctx, merged_timings = build_merged_rag_context(
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
                        rag_ctx_for_log = RagContext(
                            context_text=merged_ctx.context_text,
                            chunks_info=merged_ctx.chunks_info,
                            max_score=merged_ctx.max_score,
                        )
                        rag_timings = merged_timings
                if not use_merged or rag_ctx_for_log is None:
                    rag_ctx_for_log, rag_timings = build_rag_context(
                        last_user,
                        effective_rag_repo,
                        effective_embed_provider,
                        effective_rerank_client,
                        effective_context_chunk_chars,
                        effective_context_total_chars,
                        rag_required_keywords=rag_keywords,
                        trigger_threshold=None,
                        force_rag=force_rag,
                    )
            if rag_timings:
                set_latest_request_rag_steps(rag_timings)
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
            set_current_trace(trace)
        except Exception as e:
            _RAG_LOG.warning(f"Failed to build RAG context for logging: {e}")
            rag_context_data = None
        set_proxy_status(STATUS_PREPARING_RESPONSE)
        
        # Reuse the same RAG context for messages (single RAG call per request)
        rag_ctx = rag_ctx_for_log if (include_rag_metadata and rag_ctx_for_log) else None
        try:
            req = RagQuestionRequest(
                messages=messages,
                model=actual_model,  # Use actual_model instead of requested_model
                stream=stream,
                reasoning_level=reasoning_level,
            )
            ollama_messages, use_model = prepare_ollama_messages(
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
                reasoning_level=reasoning_level,
                rag_required_keywords=rag_keywords,
                rag_context=rag_ctx_for_log,
                trigger_threshold=None,
                force_rag=force_rag,
            )
            # Ensure use_model is not "rag-ollama" - use config model if needed
            if use_model == "rag-ollama":
                use_model = effective_ollama_model

            # Store what we send to Ollama (preview + sizes only)
            _msg_preview_limit = 300
            _ollama_messages_preview: list[dict[str, object]] = []
            for m in ollama_messages:
                if not isinstance(m, dict):
                    continue
                role = m.get("role") or ""
                content_str = m.get("content") or ""
                content_len = len(content_str)
                _ollama_messages_preview.append(
                    {
                        "role": str(role),
                        "content_length_chars": int(content_len),
                        "content_preview": content_str[:_msg_preview_limit]
                        + ("..." if content_len > _msg_preview_limit else ""),
                    }
                )
            trace["ollama"]["model"] = use_model
            trace["ollama"]["messages"] = _ollama_messages_preview
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "prepare_rag"})
            _log_rag_error("prepare_rag", e)
            return jsonify({"error": str(e)}), 500

        if tools and tool_choice_effective != "none":
            if post_tool_success_turn:
                ollama_messages.append({"role": "system", "content": _POST_TOOL_SUCCESS_SYSTEM})
            else:
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

        stream_tool_mode = bool(
            stream and tools and tool_choice_effective != "none" and not post_tool_success_turn
        )
        if stream_tool_mode:
            set_proxy_status(STATUS_RESPONSE)
            stream_start_time = time.time()
            stream_tool_error: str | None = None
            try:
                streamed_content = chat_client.chat(ollama_messages, use_model, stream=False, options=None)
            except Exception as e:
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
                    streamed_content = chat_client.chat(compact_messages or ollama_messages, use_model, stream=False, options=None)
                except Exception as e2:
                    log_webui_error("rag_routes.chat_completions", e2, {"stage": "chat_stream_tool_mode"})
                    _log_rag_error("chat_stream_tool_mode", e2)
                    stream_tool_error = str(e2)
                    streamed_content = ""
            finally:
                set_proxy_status(STATUS_IDLE)
                set_latest_request_seconds(time.time() - start_time)

            if stream_tool_error:
                # Do not fail the whole request: fallback to plain streaming branch below.
                trace["response"]["tool_mode_error"] = stream_tool_error[:500]
                set_current_trace(trace)
            edit_payload = _extract_edit_from_response(streamed_content or "")
            tool_plain_fallback = (streamed_content or "").strip()

            if (not stream_tool_error) and not edit_payload and selected_edit_tool_name:
                tool_json_instruction = _build_tool_json_instruction(
                    selected_edit_tool_name, selected_edit_tool
                )
                strict_messages: list[dict[str, object]] = []
                if tool_json_instruction:
                    strict_messages.append({"role": "system", "content": tool_json_instruction})
                strict_messages.append(
                    {
                        "role": "user",
                        "content": _strict_retry_user_content(
                            user_query or last_user or "", selected_edit_tool_name
                        ),
                    }
                )
                try:
                    retried_content = chat_client.chat(strict_messages, use_model, stream=False, options=None)
                    tool_plain_fallback = (retried_content or "").strip() or tool_plain_fallback
                    edit_payload = _extract_edit_from_response(retried_content or "")
                except Exception as e2:
                    log_webui_error("rag_routes.chat_completions", e2, {"stage": "stream_tool_mode_strict_retry"})
                    _log_rag_error("stream_tool_mode_strict_retry", e2)
                    edit_payload = None

            if (not stream_tool_error) and not edit_payload and selected_edit_tool_name:
                tool_json_instruction2 = _build_tool_json_instruction(
                    selected_edit_tool_name, selected_edit_tool
                )
                strict_messages2: list[dict[str, object]] = []
                if tool_json_instruction2:
                    strict_messages2.append({"role": "system", "content": tool_json_instruction2})
                strict_messages2.append(
                    {
                        "role": "user",
                        "content": _strict_retry_user_content(
                            user_query or last_user or "", selected_edit_tool_name
                        )
                        + " Your previous JSON was invalid or omitted required code fields (empty replacement/new_text/content). Output ONE JSON object that includes the actual code.",
                    }
                )
                try:
                    retried2 = chat_client.chat(strict_messages2, use_model, stream=False, options=None)
                    tool_plain_fallback = (retried2 or "").strip() or tool_plain_fallback
                    edit_payload = _extract_edit_from_response(retried2 or "")
                except Exception as e_strict2:
                    log_webui_error(
                        "rag_routes.chat_completions",
                        e_strict2,
                        {"stage": "stream_tool_mode_strict_retry_2"},
                    )
                    _log_rag_error("stream_tool_mode_strict_retry_2", e_strict2)

            if (not stream_tool_error) and edit_payload and selected_edit_tool_name:
                edit_payload, did_full_file_retry = _maybe_retry_edit_payload_full_file(
                    chat_client,
                    use_model,
                    user_query or last_user or "",
                    selected_edit_tool_name,
                    selected_edit_tool,
                    edit_payload,
                )
                if did_full_file_retry:
                    trace["request"]["internal_full_file_retry"] = True
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
                    set_current_trace(trace)

                    def generate_sse_tool_call():
                        oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'id': tool_call['id'], 'type': 'function', 'function': {'name': selected_edit_tool_name, 'arguments': tool_call['function']['arguments']}}]}, 'finish_reason': None}]})}\n\n"
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]})}\n\n"
                        yield "data: [DONE]\n\n"

                    return Response(
                        generate_sse_tool_call(),
                        mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                    )
            if (not stream_tool_error) and (not edit_payload) and (not tool_plain_fallback):
                # Some Ollama models occasionally return an empty string. Do not stream "nothing":
                # return a short plain-text message so the client can surface an error instead
                # of waiting on an invisible response.
                try:
                    minimal_messages: list[dict[str, object]] = []
                    # Ultra-minimal retry: strip volatile context/attachments.
                    minimal_user = _strip_context_sections(user_query or last_user or "")
                    tool_json_instruction_m = _build_tool_json_instruction(
                        selected_edit_tool_name, selected_edit_tool
                    )
                    if tool_json_instruction_m:
                        minimal_messages.append({"role": "system", "content": tool_json_instruction_m})
                    minimal_messages.append(
                        {
                            "role": "user",
                            "content": (minimal_user or (user_query or last_user or "")).strip()
                            + "\n\nReturn ONE JSON tool object if tools are enabled; otherwise 1-2 sentences.",
                        }
                    )
                    tool_plain_fallback = (
                        (chat_client.chat(minimal_messages, use_model, stream=False, options=None) or "").strip()
                    )
                except Exception:
                    tool_plain_fallback = ""
                if not tool_plain_fallback:
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
                set_current_trace(trace)

                def generate_sse_plain_text():
                    oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'content': tool_plain_fallback}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                    yield "data: [DONE]\n\n"

                return Response(
                    generate_sse_plain_text(),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )

        if stream:
            set_proxy_status(STATUS_RESPONSE)
            def generate_sse():
                oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                preview = ""
                stream_start_time = time.time()
                full_response = ""
                emitted_any = False
                total_tokens_holder = [0]
                try:
                    for content in chat_client.stream_chat(ollama_messages, use_model):
                        if content:
                            full_response += content
                            preview += content[: max(0, log_preview - len(preview))]
                            emitted_any = True
                            chunk = {
                                "id": oid,
                                "object": "chat.completion.chunk",
                                "model": use_model,
                                "choices": [
                                    {"index": 0, "delta": {"content": content}, "finish_reason": None},
                                ],
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                    if not emitted_any:
                        full_response = (
                            "Model returned an empty response; no tool call was emitted. Please retry."
                        )
                        preview = full_response[:log_preview]
                        chunk = {
                            "id": oid,
                            "object": "chat.completion.chunk",
                            "model": use_model,
                            "choices": [
                                {"index": 0, "delta": {"content": full_response}, "finish_reason": None},
                            ],
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"
                    
                    # Log streaming request
                    stream_latency_ms = int((time.time() - stream_start_time) * 1000)
                    def _approx_tokens(text: str) -> int:
                        if not text:
                            return 0
                        return max(1, int(len(text) / 4))
                    
                    prompt_text = " ".join((m.get("content") or "") for m in ollama_messages if isinstance(m, dict))
                    prompt_tokens_approx = _approx_tokens(prompt_text)
                    completion_tokens_approx = _approx_tokens(full_response)
                    total_tokens_approx = prompt_tokens_approx + completion_tokens_approx
                    total_tokens_holder[0] = total_tokens_approx

                    # Finalize trace for the UI and history
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
                    trace["steps"].append(
                        {
                            "name": "ollama_chat",
                            "duration_ms": int(stream_latency_ms),
                            "tokens_in_est": prompt_tokens_approx,
                            "tokens_out_est": completion_tokens_approx,
                        }
                    )
                    set_current_trace(trace)
                    
                    try:
                        session_manager = get_session_manager()
                        session = session_manager.get_or_create_session("proxy")
                        logs_repo = get_logs_repository()
                        log_metadata = {
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
                        }
                        logs_repo.add_log(
                            session_id="proxy",
                            level="INFO",
                            message=f"Proxy request (stream): {user_query[:100]}...",
                            source="proxy",
                            metadata=log_metadata,
                        )
                    except Exception as e:
                        _RAG_LOG.warning(f"Failed to log proxy stream request to database: {e}")
                    
                    _RAG_LOG.info(
                        "RAG response (stream) model=%s len=%s preview=%s",
                        use_model,
                        len(full_response),
                        preview[:log_preview] if preview else "",
                    )
                except Exception as e:
                    log_webui_error("rag_routes.chat_completions", e, {"stage": "stream_chat"})
                    _log_rag_error("stream_chat", e)
                    raise
                finally:
                    set_proxy_status(STATUS_IDLE)
                    set_latest_request_seconds(time.time() - start_time)
                    set_latest_request_total_tokens(total_tokens_holder[0] or None)
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"
            return Response(
                generate_sse(),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        try:
            set_proxy_status(STATUS_RESPONSE)
            content = chat_client.chat(ollama_messages, use_model, stream=False, options=None)
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "chat"})
            _log_rag_error("chat", e)
            return jsonify({"error": str(e)}), 500
        finally:
            set_proxy_status(STATUS_IDLE)
            set_latest_request_seconds(time.time() - start_time)
        latency_ms = int((time.time() - start_time) * 1000)
        _prompt_text = " ".join((m.get("content") or "") for m in ollama_messages if isinstance(m, dict))
        prompt_tokens_approx = max(1, int(len(_prompt_text) / 4))
        completion_tokens_approx = max(1, int(len(content or "") / 4))
        _total_tokens_approx = prompt_tokens_approx + completion_tokens_approx
        set_latest_request_total_tokens(_total_tokens_approx)
        content_len = len(content or "")
        content_preview = (content or "")[:log_preview]
        if content_len > log_preview:
            content_preview += "..."
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
        set_current_trace(trace)
        tool_calls: list[dict[str, object]] = []
        if (not stream) and tools and tool_choice_effective != "none" and not post_tool_success_turn:
            edit_payload = _extract_edit_from_response(content or "")
            if edit_payload and selected_edit_tool_name:
                edit_payload, did_full_file_retry = _maybe_retry_edit_payload_full_file(
                    chat_client,
                    use_model,
                    user_query or last_user or "",
                    selected_edit_tool_name,
                    selected_edit_tool,
                    edit_payload,
                )
                if did_full_file_retry:
                    trace["request"]["internal_full_file_retry"] = True
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
            if not tool_calls and selected_edit_tool_name:
                tool_json_instruction = _build_tool_json_instruction(
                    selected_edit_tool_name, selected_edit_tool
                )
                strict_messages_ns: list[dict[str, object]] = []
                if tool_json_instruction:
                    strict_messages_ns.append({"role": "system", "content": tool_json_instruction})
                strict_messages_ns.append(
                    {
                        "role": "user",
                        "content": _strict_retry_user_content(
                            user_query or last_user or "", selected_edit_tool_name
                        ),
                    }
                )
                retried_payload: dict[str, object] | None = None
                try:
                    retried_content = chat_client.chat(strict_messages_ns, use_model, stream=False, options=None)
                    retried_payload = _extract_edit_from_response(retried_content or "")
                    if retried_payload:
                        retried_payload, did_ff2 = _maybe_retry_edit_payload_full_file(
                            chat_client,
                            use_model,
                            user_query or last_user or "",
                            selected_edit_tool_name,
                            selected_edit_tool,
                            retried_payload,
                        )
                        if did_ff2:
                            trace["request"]["internal_full_file_retry"] = True
                        tool_args = _build_tool_arguments(
                            selected_tool_name=selected_edit_tool_name,
                            selected_tool=selected_edit_tool,
                            edit_payload=retried_payload,
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
                except Exception as e3:
                    log_webui_error("rag_routes.chat_completions", e3, {"stage": "non_stream_tool_mode_strict_retry"})
                    _log_rag_error("non_stream_tool_mode_strict_retry", e3)
                if not tool_calls and selected_edit_tool_name:
                    strict_messages_ns2: list[dict[str, object]] = []
                    if tool_json_instruction:
                        strict_messages_ns2.append({"role": "system", "content": tool_json_instruction})
                    strict_messages_ns2.append(
                        {
                            "role": "user",
                            "content": _strict_retry_user_content(
                                user_query or last_user or "", selected_edit_tool_name
                            )
                            + " Your previous JSON was invalid or omitted required code fields (empty replacement/new_text/content). Output ONE JSON object that includes the actual code.",
                        }
                    )
                    try:
                        retried2 = chat_client.chat(strict_messages_ns2, use_model, stream=False, options=None)
                        retried_payload2 = _extract_edit_from_response(retried2 or "")
                        if retried_payload2:
                            retried_payload2, did_ff3 = _maybe_retry_edit_payload_full_file(
                                chat_client,
                                use_model,
                                user_query or last_user or "",
                                selected_edit_tool_name,
                                selected_edit_tool,
                                retried_payload2,
                            )
                            if did_ff3:
                                trace["request"]["internal_full_file_retry"] = True
                            tool_args = _build_tool_arguments(
                                selected_tool_name=selected_edit_tool_name,
                                selected_tool=selected_edit_tool,
                                edit_payload=retried_payload2,
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
                    except Exception as e4:
                        log_webui_error(
                            "rag_routes.chat_completions",
                            e4,
                            {"stage": "non_stream_tool_mode_strict_retry_2"},
                        )
                        _log_rag_error("non_stream_tool_mode_strict_retry_2", e4)

        trace["response"]["tool_calls_count"] = len(tool_calls)
        if tool_calls:
            trace["response"]["tool_calls"] = tool_calls
            set_current_trace(trace)
        choice = {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None if tool_calls else content,
                **({"tool_calls": tool_calls} if tool_calls else {}),
            },
            "finish_reason": "tool_calls" if tool_calls else "stop",
        }
        response_data = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": 0,
            "model": use_model,
            "choices": [choice],
        }
        
        # Add RAG metadata if requested
        if include_rag_metadata and rag_ctx:
            response_data["rag_metadata"] = {
                "chunks_info": rag_ctx.chunks_info,
                "max_score": rag_ctx.max_score,
                "chunks_count": len(rag_ctx.chunks_info),
            }

        # Persist trace for non-stream requests
        try:
            session_manager = get_session_manager()
            session = session_manager.get_or_create_session("proxy")
            logs_repo = get_logs_repository()
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
            }
            logs_repo.add_log(
                session_id="proxy",
                level="INFO",
                message=f"Proxy request: {user_query[:100]}...",
                source="proxy",
                metadata=log_metadata,
            )
        except Exception as e:
            _RAG_LOG.warning(f"Failed to log proxy non-stream request to database: {e}")
        
        return jsonify(response_data)

    # Open WebUI status/start/stop: same pattern as RAG (docker), registered on app so always available
    from api.http.webui_routes import (
        open_webui_status,
        open_webui_start,
        open_webui_stop,
        webui_bp,
    )
    app.add_url_rule(
        "/api/webui/open-webui/status",
        view_func=open_webui_status,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/webui/open-webui/start",
        view_func=open_webui_start,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/webui/open-webui/stop",
        view_func=open_webui_stop,
        methods=["POST"],
    )

    app.register_blueprint(webui_bp)

    @app.route("/v1/files/apply-edit", methods=["POST"])
    def apply_file_edit() -> Response | tuple[Response, int]:
        """
        Apply direct file edit inside workspace by explicit line/column range.
        Expected body: { file_path, range:{start_line,start_col,end_line,end_col}, new_text, dry_run? }.
        """
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception:
            return jsonify({"ok": False, "error": "Invalid JSON"}), 400

        try:
            file_path_raw = str(body.get("file_path") or "").strip()
            range_data = body.get("range") or {}
            new_text = body.get("new_text")
            patch_text = body.get("patch")
            dry_run = bool(body.get("dry_run", False))
            if patch_text:
                return jsonify({"ok": False, "error": "patch apply is not supported yet"}), 400
            if not isinstance(range_data, dict):
                return jsonify({"ok": False, "error": "range must be an object"}), 400
            if not isinstance(new_text, str):
                return jsonify({"ok": False, "error": "new_text is required"}), 400

            resolved = _resolve_workspace_path(file_path_raw)
            if not resolved.exists():
                return jsonify({"ok": False, "error": "file does not exist"}), 404
            original = resolved.read_text(encoding="utf-8")

            # If end_col is huge (inferred unknown), clamp to line length + 1.
            if "end_col" in range_data:
                lines = original.splitlines(keepends=True)
                end_line = int(range_data.get("end_line") or 0)
                if 1 <= end_line <= len(lines):
                    end_col = int(range_data.get("end_col") or 1)
                    if end_col > len(lines[end_line - 1]) + 1:
                        range_data = dict(range_data)
                        range_data["end_col"] = len(lines[end_line - 1]) + 1

            updated = _replace_text_range(original, range_data, new_text)
            if not dry_run:
                resolved.write_text(updated, encoding="utf-8")
            try:
                get_logs_repository().add_log(
                    session_id="proxy",
                    level="INFO",
                    message=f"Apply edit: {resolved}",
                    source="proxy.apply_edit",
                    metadata={
                        "file_path": str(resolved),
                        "dry_run": dry_run,
                        "range": range_data,
                        "new_text_len": len(new_text),
                    },
                )
            except Exception:
                pass

            return jsonify(
                {
                    "ok": True,
                    "applied": not dry_run,
                    "dry_run": dry_run,
                    "file_path": str(resolved),
                    "preview": updated[:2000],
                }
            )
        except ValueError as exc:
            try:
                get_logs_repository().add_log(
                    session_id="proxy",
                    level="ERROR",
                    message=f"Apply edit failed: {exc}",
                    source="proxy.apply_edit",
                    metadata={"error": str(exc)},
                )
            except Exception:
                pass
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            _RAG_LOG.exception("apply-file-edit failed")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/v1/external-docs/ingest", methods=["POST"])
    def external_docs_ingest() -> tuple[Response, int]:
        """Trigger ingest of an external source (e.g. tm_architecture) into its collection."""
        if not _EXTERNAL_DOCS_RAG_AVAILABLE:
            return jsonify({"error": "external_docs_rag module not available"}), 503
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception:
            return jsonify({"error": "Invalid JSON"}), 400
        source_id = (body.get("source_id") or "").strip()
        if not source_id:
            return jsonify({"error": "source_id is required"}), 400
        try:
            from external_docs_rag.config_loader import load_external_sources
            from external_docs_rag.application.use_cases import ingest_source_to_collection
            from external_docs_rag.infrastructure import HttpFetchClient, QdrantChunkSink
            from external_docs_rag.infrastructure.ollama_embed_adapter import OllamaEmbedAdapter
            import os
            sources = load_external_sources()
            source = next((s for s in sources if s.id == source_id), None)
            if not source:
                return jsonify({"error": f"Source '{source_id}' not found"}), 404
            try:
                qdrant_url = get_qdrant_url()
            except Exception:
                qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
            result = ingest_source_to_collection(
                source,
                HttpFetchClient(),
                QdrantChunkSink(base_url=qdrant_url),
                OllamaEmbedAdapter(),
            )
            return jsonify({
                "source_id": result.source_id,
                "collection_name": result.collection_name,
                "documents_fetched": result.documents_fetched,
                "chunks_indexed": result.chunks_indexed,
                "errors": result.errors,
            }), 200
        except Exception as e:
            _RAG_LOG.exception("external-docs ingest failed: %s", e)
            return jsonify({"error": str(e)}), 500

    return app


__all__ = ["create_app"]
