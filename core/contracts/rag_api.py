"""
RAG service HTTP/JSON contract.

DTOs and endpoint descriptions for clients (e.g. webui_backend) calling rag_service (package under CoreModules/RagService).
No implementation; used for typing and OpenAPI generation.

For the **public OpenAI-compatible** surface (``/v1/chat/completions`` vs ``/v1/completions``), see
[openai_proxy_api](openai_proxy_api.py).
"""

from __future__ import annotations

from typing import Any

# Request/response shapes for /v1/chat/completions (OpenAI-compatible subset)
# Clients send:
# {
#   "messages": [...],
#   "model": "...",
#   "stream": false,
#   "reasoning_level": "...",
#   "include_rag_metadata": false,
#   "tools": [...],                 # optional OpenAI-style tools (functions)
#   "tool_choice": "auto|none|..."  # optional tool choice
# }
# Service returns:
# {
#   "id",
#   "object",
#   "model",
#   "choices": [{
#      "message": { "role", "content", "tool_calls"?: [...] },
#      "finish_reason": "stop|tool_calls"
#   }],
#   "rag_metadata"?: {...}
# }


def rag_chat_request_shape() -> dict[str, Any]:
    """Minimal shape of POST /v1/chat/completions request body."""
    return {
        "messages": "list[dict] (OpenAI message format)",
        "model": "str (optional, default from config)",
        "stream": "bool (optional, default false)",
        "reasoning_level": "str | null (optional)",
        "include_rag_metadata": "bool (optional, default false)",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "apply_file_edit",
                    "description": "Apply direct file edit by range or patch",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "range": {
                                "type": "object",
                                "properties": {
                                    "start_line": {"type": "integer"},
                                    "start_col": {"type": "integer"},
                                    "end_line": {"type": "integer"},
                                    "end_col": {"type": "integer"},
                                },
                            },
                            "new_text": {"type": "string"},
                            "patch": {"type": "string"},
                            "dry_run": {"type": "boolean"},
                        },
                    },
                },
            }
        ],
        "tool_choice": "str | dict (optional)",
    }


def rag_chat_response_shape() -> dict[str, Any]:
    """Minimal shape of POST /v1/chat/completions response (non-stream)."""
    return {
        "id": "str",
        "object": "chat.completion",
        "model": "str",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "str | null",
                    "tool_calls": "optional list[OpenAI tool_call]",
                },
                "finish_reason": "stop | tool_calls",
            }
        ],
        "rag_metadata": "optional: { chunks_info, max_score, chunks_count }",
    }


def rag_file_apply_edit_shape() -> dict[str, Any]:
    """Request/response shape for POST /v1/files/apply-edit."""
    return {
        "request": {
            "file_path": "str (relative to workspace root)",
            "range": {
                "start_line": "int (1-based)",
                "start_col": "int (1-based)",
                "end_line": "int (1-based)",
                "end_col": "int (1-based, inclusive)",
            },
            "new_text": "str (required when patch not provided)",
            "patch": "str (optional unified diff)",
            "dry_run": "bool (optional, default false)",
        },
        "response": {
            "ok": "bool",
            "file_path": "str",
            "applied": "bool",
            "preview": "str (optional)",
            "error": "str (optional)",
        },
    }


__all__ = ["rag_chat_request_shape", "rag_chat_response_shape", "rag_file_apply_edit_shape"]
