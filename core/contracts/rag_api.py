"""
RAG service HTTP/JSON contract.

DTOs and endpoint descriptions for clients (e.g. webui_backend) calling rag_service.
No implementation; used for typing and OpenAPI generation.
"""

from __future__ import annotations

from typing import Any

# Request/response shapes for /v1/chat/completions (OpenAI-compatible subset)
# Clients send: { "messages": [...], "model": "...", "stream": false, "reasoning_level": "...", "include_rag_metadata": false }
# Service returns: { "id", "object", "model", "choices": [{ "message": { "role", "content" }, "finish_reason" }], "rag_metadata"?: {...} }


def rag_chat_request_shape() -> dict[str, Any]:
    """Minimal shape of POST /v1/chat/completions request body."""
    return {
        "messages": "list[dict] (OpenAI message format)",
        "model": "str (optional, default from config)",
        "stream": "bool (optional, default false)",
        "reasoning_level": "str | null (optional)",
        "include_rag_metadata": "bool (optional, default false)",
    }


def rag_chat_response_shape() -> dict[str, Any]:
    """Minimal shape of POST /v1/chat/completions response (non-stream)."""
    return {
        "id": "str",
        "object": "chat.completion",
        "model": "str",
        "choices": [{"message": {"role": "assistant", "content": "str"}, "finish_reason": "str"}],
        "rag_metadata": "optional: { chunks_info, max_score, chunks_count }",
    }


__all__ = ["rag_chat_request_shape", "rag_chat_response_shape"]
