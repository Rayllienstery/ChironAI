"""
Pipeline step implementations. All rules come from step params; no hardcoded data.
"""

from __future__ import annotations

import re
from typing import Any

# parse_and_strip_meta_block is used only in strip_meta_block step; import at runtime in runner
# to avoid circular or path issues when md_indexer is used from WebUI.


def step_strip_meta_block(md: str, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Remove leading <!-- meta ... --> block; return (meta, body)."""
    from domain.services.markdown_meta import parse_and_strip_meta_block

    meta, body = parse_and_strip_meta_block(md)
    return (meta, body)


def step_delete_lines_exact(md: str, params: dict[str, Any]) -> str:
    """Remove lines that exactly match one of the given strings (after strip)."""
    if not md:
        return ""
    lines_raw = params.get("lines") or []
    lines_set = {s.strip() for s in lines_raw if isinstance(s, str)}
    case_sensitive = params.get("case_sensitive", False)
    if not case_sensitive:
        lines_set = {s.lower() for s in lines_set}
    result = []
    for ln in md.split("\n"):
        stripped = ln.strip()
        check = stripped if case_sensitive else stripped.lower()
        if check in lines_set:
            continue
        result.append(ln)
    return _collapse_blank_lines("\n".join(result))


def step_delete_lines_containing(md: str, params: dict[str, Any]) -> str:
    """Remove lines containing any of the given substrings."""
    if not md:
        return ""
    substrings = params.get("substrings") or []
    case_sensitive = params.get("case_sensitive", False)
    result = []
    for ln in md.split("\n"):
        content = ln if case_sensitive else ln.lower()
        if any(
            (s in content) for s in substrings if isinstance(s, str)
        ):
            continue
        result.append(ln)
    return _collapse_blank_lines("\n".join(result))


def step_delete_lines_regex(md: str, params: dict[str, Any]) -> str:
    """Remove lines that match the given regex (whole line)."""
    if not md:
        return ""
    pattern = params.get("pattern")
    if not pattern:
        return md
    try:
        rx = re.compile(pattern)
    except re.error:
        return md
    result = [ln for ln in md.split("\n") if not rx.search(ln)]
    return _collapse_blank_lines("\n".join(result))


def step_delete_range_regex(md: str, params: dict[str, Any]) -> str:
    """Remove span from start_regex to end_regex (or EOF). Optionally include/exclude boundaries."""
    if not md:
        return ""
    start_regex = params.get("start_regex")
    if not start_regex:
        return md
    end_regex = params.get("end_regex")
    include_start = params.get("include_start", True)
    include_end = params.get("include_end", False)
    try:
        start_rx = re.compile(start_regex, re.MULTILINE)
        end_rx = re.compile(end_regex, re.MULTILINE) if end_regex else None
    except re.error:
        return md

    out_parts = []
    pos = 0
    text = md
    while True:
        m = start_rx.search(text, pos)
        if not m:
            out_parts.append(text[pos:])
            break
        # From start of match (or end of match if not include_start) to end_regex or EOF
        if include_start:
            cut_start = m.start()
        else:
            cut_start = m.end()
        out_parts.append(text[pos:cut_start])
        search_from = m.end()
        if end_rx:
            end_m = end_rx.search(text, search_from)
            if end_m:
                if include_end:
                    pos = end_m.end()
                else:
                    pos = end_m.start()
            else:
                pos = len(text)
        else:
            pos = len(text)
    return _collapse_blank_lines("".join(out_parts))


def step_delete_regex_match(md: str, params: dict[str, Any]) -> str:
    """Find all non-overlapping matches of pattern and remove each."""
    if not md:
        return ""
    pattern = params.get("pattern")
    if not pattern:
        return md
    flags = re.DOTALL
    if "(?m)" in pattern or "(?s)" in pattern or "(?ms)" in pattern:
        pass
    else:
        flags = re.DOTALL
    try:
        rx = re.compile(pattern, flags)
    except re.error:
        return md
    return _collapse_blank_lines(rx.sub("", md))


def step_strip_sections_by_heading(md: str, params: dict[str, Any]) -> str:
    """Remove sections whose heading (normalized: no #, lower) equals or starts with one of the list."""
    if not md:
        return ""
    headings_raw = params.get("headings") or []
    noise = frozenset(s.strip().lower() for s in headings_raw if isinstance(s, str) and s.strip())
    if not noise:
        return md
    lines = md.split("\n")
    out = []
    skip = False
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("#"):
            heading = re.sub(r"^#+\s*", "", stripped).strip().lower()
            if any(
                heading == n or heading.startswith(n + " ") or heading.startswith(n + "(")
                for n in noise
            ):
                skip = True
                continue
            skip = False
        if skip:
            continue
        out.append(ln)
    return _collapse_blank_lines("\n".join(out))


def step_normalize_whitespace(md: str, params: dict[str, Any]) -> str:
    """Strip trailing WS per line, trim outer blank lines, collapse 2+ spaces (respect fenced/code)."""
    if not md:
        return ""
    lines = md.split("\n")
    lines = [ln.rstrip() for ln in lines]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    in_fenced = False
    result = []
    for ln in lines:
        if ln.strip().startswith("```"):
            in_fenced = not in_fenced
            result.append(ln)
            continue
        if in_fenced:
            result.append(ln)
            continue
        if len(ln) - len(ln.lstrip()) >= 4 and ln.strip():
            result.append(ln)
            continue
        result.append(re.sub(r" {2,}", " ", ln))
    return "\n".join(result)


def step_wrap_indented_code(md: str, params: dict[str, Any]) -> str:
    """Wrap non-fenced 4-space-indented blocks in fenced code blocks."""
    if not md:
        return ""
    language = params.get("language") or ""
    try:
        min_block_lines = int(params.get("min_block_lines") or 1)
    except (TypeError, ValueError):
        min_block_lines = 1
    lines = md.split("\n")
    result: list[str] = []
    in_fenced = False
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fenced = not in_fenced
            result.append(line)
            i += 1
            continue
        if in_fenced:
            result.append(line)
            i += 1
            continue
        indent = len(line) - len(stripped)
        if indent >= 4 and stripped:
            block_lines: list[str] = []
            while i < n:
                cur = lines[i]
                cur_stripped = cur.lstrip()
                cur_indent = len(cur) - len(cur_stripped)
                if cur_indent >= 4 and cur_stripped:
                    block_lines.append(cur)
                    i += 1
                else:
                    break
            if len(block_lines) >= min_block_lines:
                fence_open = "```" + language if language else "```"
                result.append(fence_open)
                result.extend(block_lines)
                result.append("```")
            else:
                result.extend(block_lines)
        else:
            result.append(line)
            i += 1
    return "\n".join(result)


def step_replace_regex(md: str, params: dict[str, Any]) -> str:
    """Replace each match of pattern with replacement string."""
    if not md:
        return ""
    pattern = params.get("pattern")
    replacement = params.get("replacement", "")
    if not pattern:
        return md
    try:
        rx = re.compile(pattern)
    except re.error:
        return md
    return rx.sub(replacement, md)


# Defaults for pipeline JSON and for prepare fallback when md_indexer runner is unavailable.
DEFAULT_REJECT_LOW_SIGNAL_PARAMS: dict[str, Any] = {
    "min_chars": 120,
    "min_words": 5,
    "min_alpha_ratio": 0.12,
}


def step_reject_low_signal_body(md: str, params: dict[str, Any]) -> str:
    """
    Drop body (return empty string) if text looks too thin for RAG: short, too few words,
    or mostly non-letters (e.g. link/nav soup). Keeps pages that are short but dense prose.

    Params (all optional; merged over DEFAULT_REJECT_LOW_SIGNAL_PARAMS):
      min_chars: minimum stripped character count (default 120).
      min_words: minimum whitespace-separated words; 0 disables (default from DEFAULT).
      min_alpha_ratio: min fraction of non-space chars that are letters; 0 disables (default from DEFAULT).
    """
    body = md or ""
    stripped = body.strip()
    if not stripped:
        return ""

    p = {**DEFAULT_REJECT_LOW_SIGNAL_PARAMS, **(params or {})}
    try:
        min_chars = max(0, int(p.get("min_chars", 120)))
    except (TypeError, ValueError):
        min_chars = 120
    try:
        min_words = int(p.get("min_words", 5))
    except (TypeError, ValueError):
        min_words = 5
    try:
        min_alpha_ratio = float(p.get("min_alpha_ratio", 0.12))
    except (TypeError, ValueError):
        min_alpha_ratio = 0.12

    if len(stripped) < min_chars:
        return ""

    if min_words > 0:
        words = stripped.split()
        if len(words) < min_words:
            return ""

    if min_alpha_ratio > 0:
        alpha = sum(1 for c in stripped if c.isalpha())
        non_ws = sum(1 for c in stripped if not c.isspace())
        if non_ws == 0 or alpha / non_ws < min_alpha_ratio:
            return ""

    return body


def _collapse_blank_lines(text: str) -> str:
    """Replace 3+ newlines with 2 and strip."""
    return re.sub(r"\n{3,}", "\n\n", text).strip()
