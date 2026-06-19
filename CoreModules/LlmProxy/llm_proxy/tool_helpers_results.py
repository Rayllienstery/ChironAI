"""Tool-result classification helpers for proxy tools."""

from __future__ import annotations

import base64
import json
import re
import shlex
from pathlib import Path

from llm_proxy.tool_helpers_edit import (
    _extract_file_path_from_user_text,
    _extract_tool_name,
    _get_tool_by_name,
    _is_edit_like_tool_name,
    _normalize_tool_path,
    _strip_context_sections,
)


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
    return bool(re.search(r"^-[^\\n]", t, flags=re.MULTILINE) and not re.search(r"^\\+[^\\n]", t, flags=re.MULTILINE))


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
    return bool("diff" in low and re.search(r"^\+[^\n]", t, flags=re.MULTILINE))


def _prior_tool_messages_include_successful_edit(messages: list[object]) -> bool:
    """Any tool_result before the last one in the transcript looks like a successful edit."""
    contents = _collect_tool_result_contents_in_order(messages)
    if len(contents) < 2:
        return False
    return any(_tool_content_indicates_successful_edit(c) for c in contents[:-1])

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
    prop_keys = set(str(k) for k in props) if isinstance(props, dict) else set()
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


