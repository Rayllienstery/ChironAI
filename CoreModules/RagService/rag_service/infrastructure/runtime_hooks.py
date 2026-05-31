"""Process-wide hooks for resolving the extension-backed LLM runtime."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_llm_runtime_getter: Callable[[], Any | None] | None = None


def set_llm_runtime_getter(getter: Callable[[], Any | None] | None) -> None:
    global _llm_runtime_getter
    _llm_runtime_getter = getter


def get_llm_runtime_getter() -> Callable[[], Any | None] | None:
    return _llm_runtime_getter


def get_llm_runtime() -> Any | None:
    getter = _llm_runtime_getter
    if getter is None:
        return None
    try:
        return getter()
    except Exception:
        return None


__all__ = ["get_llm_runtime", "get_llm_runtime_getter", "set_llm_runtime_getter"]
