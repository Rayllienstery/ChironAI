"""
OpenAI-compatible HTTP surface implemented by **LlmProxy** (``/v1/*``).

CoreUI and external clients must pick the endpoint that matches semantics:

- **Chat** — RAG, tools, streaming, WebUI-derived settings (primary assistant use case).
- **Responses/Messages** — compatibility adapters that normalize to provider-backed chat.

See [CoreModules/LlmProxy/README.md](CoreModules/LlmProxy/README.md) for behaviour details.
"""

from __future__ import annotations

from typing import TypedDict

# Paths relative to proxy base URL (served on the main server port).
V1_MODELS_PATH: str = "/v1/models"
V1_CHAT_COMPLETIONS_PATH: str = "/v1/chat/completions"
V1_MESSAGES_PATH: str = "/v1/messages"
V1_RESPONSES_PATH: str = "/v1/responses"


class OpenAiProxyCapability(TypedDict):
    """Short reference for docs and UI copy; not a wire format."""

    path: str
    rag: bool
    streaming: bool
    tools: bool
    notes: str


OPENAI_PROXY_CAPABILITIES: tuple[OpenAiProxyCapability, ...] = (
    {
        "path": V1_CHAT_COMPLETIONS_PATH,
        "rag": True,
        "streaming": True,
        "tools": True,
        "notes": "Primary path; OpenAI chat messages format.",
    },
    {
        "path": V1_MESSAGES_PATH,
        "rag": True,
        "streaming": True,
        "tools": True,
        "notes": "Anthropic Messages compatibility adapter over provider-backed chat.",
    },
    {
        "path": V1_RESPONSES_PATH,
        "rag": True,
        "streaming": True,
        "tools": True,
        "notes": "OpenAI Responses compatibility adapter over provider-backed chat.",
    },
    {
        "path": V1_MODELS_PATH,
        "rag": False,
        "streaming": False,
        "tools": False,
        "notes": "Lists configured proxy builds and logical provider models.",
    },
)


__all__ = [
    "V1_MODELS_PATH",
    "V1_CHAT_COMPLETIONS_PATH",
    "V1_MESSAGES_PATH",
    "V1_RESPONSES_PATH",
    "OpenAiProxyCapability",
    "OPENAI_PROXY_CAPABILITIES",
]
