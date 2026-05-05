"""Isolated helpers for chat completion orchestration (trace skeleton, tool-loop policy)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_TOOL_LOOP_FINALIZE_WHITELIST = frozenset(
    {"shell", "bash", "web_search", "file_search", "grep", "read", "glob", "task"}
)


def _new_chat_trace_dict(*, trace_id: str) -> dict[str, Any]:
    """Initial ``trace`` object for a single proxy request."""
    return {
        "trace_id": trace_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request": {},
        "internet": {},
        "rag": {},
        "ollama": {},
        "response": {},
        "steps": [],
        "pipeline_steps": [],
    }


def _tool_loop_needs_finalize_nudge(tool_loop_stats: dict[str, Any] | None) -> bool:
    """Recommend a finalize nudge after many single-tool rounds (any tool name possible)."""
    if not isinstance(tool_loop_stats, dict):
        return False
    singles = int(tool_loop_stats.get("single_tool_rounds") or 0)
    rounds = int(tool_loop_stats.get("rounds") or 0)
    dominant = str(tool_loop_stats.get("dominant_tool") or "").strip().lower()
    dom_rounds = int(tool_loop_stats.get("dominant_tool_rounds") or 0)
    if rounds >= 25:
        return True
    if singles < 3:
        return False
    if dominant in _TOOL_LOOP_FINALIZE_WHITELIST and dom_rounds >= 3:
        return True
    if dominant and dom_rounds >= 8:
        return True
    return False
