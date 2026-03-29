"""Tool/edit helpers for OpenAI-compatible proxy chat."""

from __future__ import annotations

import base64
import json
import re
import shlex
from pathlib import Path
from urllib.parse import unquote

from llm_proxy.workspace import workspace_root as _workspace_root

_APPLY_EDIT_TOOL_NAME = "apply_file_edit"


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


_MD_LINE_ANCHOR_RE = re.compile(r"\.md[^\s)\]]*#L(\d+):(\d+)", re.IGNORECASE)


def _workspace_doc_refactor_intent(user_text: str) -> bool:
    """
    True when the user is clearly reorganizing repo docs (move lines to another .md),
    not asking Apple/framework questions. Skips RAG + web supplement to avoid noise.
    """
    t = user_text or ""
    low = t.lower()
    if "file://" not in low and "[@" not in t:
        return False
    if ".md" not in low and ".markdown" not in low:
        return False
    has_span = _extract_line_span_from_user_text(t) is not None
    m = _MD_LINE_ANCHOR_RE.search(t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        has_span = has_span or (a >= 1 and b >= 1 and a <= b)
    if not has_span:
        return False
    return bool(
        "новый файл" in low
        or "вынеси" in low
        or "вынести" in low
        or "перенеси" in low
        or "отдельный файл" in low
        or "new file" in low
        or "extract to" in low
        or "move to" in low
        or "split into" in low
    )


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
    "Ð´Ð¾Ð±Ð°Ð²",
    "Ð²ÑÑ‚Ð°Ð²",
    "Ð´Ð»Ñ ÐºÐ°Ð¶Ð´Ð¾Ð³Ð¾",
    "ÐµÑ‰Ñ‘ ",
    "ÐµÑ‰Ðµ ",
)
_SHRINK_OR_REPLACE_MARKERS = (
    "ÑƒÐ´Ð°Ð»Ð¸",
    "delete ",
    "remove ",
    "ÑÐ¾Ð¶Ð¼Ð¸",
    "shrink",
    "replace whole",
    "Ð¿ÐµÑ€ÐµÐ¿Ð¸ÑˆÐ¸",
    "rewrite ",
    "replace entire",
    "Ð¾Ñ‡Ð¸ÑÑ‚Ð¸",
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
    think: bool | str | None = None,
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
        "keep all lines that should remain and apply the user's editâ€”do not send only the new loop/block."
    )
    messages: list[dict[str, object]] = []
    if tool_json_instruction:
        messages.append({"role": "system", "content": tool_json_instruction})
    messages.append({"role": "user", "content": user_part + fix})
    try:
        raw = chat_client.chat(messages, use_model, stream=False, options=None, think=think)
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
    markers = ["create file", "generate file", "new file", "ÑÐ¾Ð·Ð´Ð°Ð¹ Ñ„Ð°Ð¹Ð»", "ÑÐ³ÐµÐ½ÐµÑ€Ð¸Ñ€ÑƒÐ¹ Ñ„Ð°Ð¹Ð»", "ÑÐ¾Ð·Ð´Ð°Ñ‚ÑŒ Ñ„Ð°Ð¹Ð»"]
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
    new_text = str(
        edit_payload.get("new_text")
        or edit_payload.get("content")
        or edit_payload.get("replacement")
        or ""
    )
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

    # Models often return mode=overwrite together with a line range. Some IDEs treat overwrite as
    # "replace the whole file", ignoring range, which truncates the file to the fragment.
    if (
        mode_value == "overwrite"
        and has_range
        and ("edit_file" in tool_name_l or "apply_file_edit" in tool_name_l)
    ):
        try:
            fp_for_exists2 = file_path
            if isinstance(fp_for_exists2, str) and fp_for_exists2.startswith("file:///"):
                fp_for_exists2 = fp_for_exists2[8:]
            p2 = Path(fp_for_exists2)
            exists2 = p2.exists() if p2.is_absolute() else (_workspace_root() / fp_for_exists2).exists()
        except Exception:
            exists2 = False
        if exists2:
            mode_value = "edit"

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
            " Required: non-empty `replacement` with the full multi-line text that replaces the userâ€™s selected "
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


