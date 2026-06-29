"""Edit intent, path, and selection helpers for proxy tools."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

from llm_proxy.workspace import workspace_root as _workspace_root

_APPLY_EDIT_TOOL_NAME = "apply_file_edit"


def _resolve_workspace_path(file_path: str) -> Path:
    if not file_path or not str(file_path).strip():
        raise ValueError("file_path is required")
    root = _workspace_root()
    candidate = Path(file_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("file_path points outside workspace") from exc
    return resolved


def _normalize_new_text_line_endings_for_file(original: str, new_text: str) -> str:
    """
    If the file on disk primarily uses CRLF but the model sent LF-only new_text, convert new_text to CRLF
    so range replacements do not mix line endings (reduces follow-up \"replace not found\" loops in clients).
    """
    if not original or not new_text or "\r\n" in new_text:
        return new_text
    sample = original[:8192]
    crlf = sample.count("\r\n")
    lf_only = sample.count("\n") - crlf
    if crlf <= lf_only or "\n" not in new_text:
        return new_text
    return new_text.replace("\r\n", "\n").replace("\n", "\r\n")


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
        "new file" in low
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


def _collect_ordered_file_uris(user_text: str) -> list[str]:
    """Distinct ``file:`` URIs in document order (fragment stripped; stable for multi-file user turns)."""
    raw = user_text or ""
    out: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"file:///[^\s)#]+", raw, re.IGNORECASE):
        u = (m.group(0) or "").strip().split("#", 1)[0].strip()
        if not u:
            continue
        key = u.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    if not out:
        for m in re.finditer(r"file://[^\s)#]+", raw, re.IGNORECASE):
            u = (m.group(0) or "").strip().split("#", 1)[0].strip()
            if u.lower().startswith("file:///"):
                continue
            key = u.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(u)
    return out


def _user_intent_copy_or_append_across_files(user_text: str) -> bool:
    """User likely edits a *destination* file (second ref), not the primary attachment."""
    low = (user_text or "").lower()
    for needle in (
        "to the end of",
        "copy to",
        "append to",
        "paste to",
        "add to the end",
        "into the end",
    ):
        if needle in low:
            return True
    return False


def _extract_file_path_for_edit_tool_precedence(user_text: str) -> str | None:
    """
    Path hint for `_build_tool_arguments`: when the user names two files and asks to copy/append
    into another file, the *last* ``file:`` URI is usually the edit target (destination).
    Otherwise fall back to the first reference (legacy behavior).
    """
    if _user_intent_copy_or_append_across_files(user_text):
        uris = _collect_ordered_file_uris(user_text)
        if len(uris) >= 2:
            return uris[-1]
    return _extract_file_path_from_user_text(user_text)


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
            f"CoreModules/CoreUI/src/{hint}",
            f"src/{hint}",
            f"Core/data/webui/{hint}",
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


def _get_tool_by_name(tools: list[object], name: str | None) -> dict[str, object] | None:
    if not name:
        return None
    for t in tools:
        if not isinstance(t, dict):
            continue
        if _extract_tool_name(t) == name:
            return t
    return None



def _is_edit_like_tool_name(name: str) -> bool:
    n = (name or "").lower()
    return any(x in n for x in ("edit", "replace", "write", "patch", "apply", "save"))



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
    if (
        not props
        and not req_set
        and _is_edit_like_tool_name(tool_name)
        and "terminal" not in (tool_name or "").lower()
    ):
        return True

    text_keys = ("content", "new_text", "replacement", "text", "new_content", "patch")
    if any(k in props or k in req_set for k in text_keys):
        return True

    paths_def = props.get("paths")
    if not isinstance(paths_def, dict):
        # Zed frequently provides partial schemas (e.g. edit_file without content field),
        # while still accepting content/new_text at runtime. For edit-like tools, prefer
        # attempting a tool call over hard-failing here.
        return bool(_is_edit_like_tool_name(tool_name) and "terminal" not in (tool_name or "").lower())
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
        if isinstance(item_props, dict) and any(
            k in item_props for k in ("content", "new_text", "text", "replacement", "new_content", "patch")
        ):
            return True
        item_req = items.get("required")
        if isinstance(item_req, list) and any(
            str(x) in ("content", "new_text", "text", "replacement", "new_content", "patch") for x in item_req
        ):
            return True
    return False


