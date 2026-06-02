"""Provider capability helpers used by OpenAI-compatible chat mapping."""

from __future__ import annotations


def get_cached_ollama_capabilities(model: str, chat_url: str) -> frozenset[str] | None:
    _ = (model, chat_url)
    return None


def caps_supports_tools(caps: frozenset[str]) -> bool:
    return "tools" in caps


def caps_supports_thinking(caps: frozenset[str]) -> bool:
    return "thinking" in caps or "think" in caps


def ollama_native_think_troublesome_model(model_name: str | None) -> bool:
    return "qwen3" in (model_name or "").lower()


def chat_error_suggests_no_tools(exc: BaseException) -> bool:
    return "does not support tools" in str(exc).lower()


def chat_error_suggests_no_think(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "does not support think" in s or "unsupported think" in s or "think is not supported" in s
