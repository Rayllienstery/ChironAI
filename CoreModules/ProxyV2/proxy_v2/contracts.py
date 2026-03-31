"""Injectable wiring: host supplies Ollama URLs, format bridge, and optional delegates."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any


@dataclass
class ProxyV2Wiring:
    """All host-specific behavior is injected; `proxy_v2` does not import application code."""

    get_ollama_chat_url: Callable[[], str]
    get_pinned_model: Callable[[], str]
    get_default_chat_options: Callable[[], dict[str, Any]]
    openai_messages_to_ollama: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    ollama_tools_from_openai: Callable[[list[dict[str, Any]] | None], list[dict[str, Any]] | None]
    ollama_message_to_openai_assistant: Callable[[dict[str, Any]], dict[str, Any]]
    openai_finish_reason_from_ollama: Callable[[dict[str, Any]], str]
    chat_api: Callable[[dict[str, Any]], dict[str, Any]]
    iter_chat_stream_openai_parts: Callable[[dict[str, Any]], Iterator[tuple[str, str]]]
    chat_api_stream_final: Callable[[dict[str, Any]], dict[str, Any]]
    host_apply_file_edit: Callable[[], Any] | None = None
    host_external_docs_ingest: Callable[[], Any] | None = None
