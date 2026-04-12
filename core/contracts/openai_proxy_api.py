"""
OpenAI-compatible HTTP surface implemented by **LlmProxy** (``/v1/*``).

CoreUI and external clients must pick the endpoint that matches semantics:

- **Chat** — RAG, tools, streaming, WebUI-derived settings (primary assistant use case).
- **Completions** — legacy ``prompt``/``input`` → Ollama ``/api/generate``; **no RAG**, no WebUI prompt template.

See [CoreModules/LlmProxy/README.md](CoreModules/LlmProxy/README.md) for behaviour details.
"""

from __future__ import annotations

from typing import Literal, TypedDict

# Paths relative to proxy base URL (same blueprint on main port and optional build_proxy port).
V1_MODELS_PATH: str = "/v1/models"
V1_CHAT_COMPLETIONS_PATH: str = "/v1/chat/completions"
V1_COMPLETIONS_PATH: str = "/v1/completions"


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
        "path": V1_COMPLETIONS_PATH,
        "rag": False,
        "streaming": True,
        "tools": False,
        "notes": "Legacy OpenAI completions; Ollama generate. Used e.g. by Zed edit prediction.",
    },
    {
        "path": V1_MODELS_PATH,
        "rag": False,
        "streaming": False,
        "tools": False,
        "notes": "Lists Ollama tags plus optional LLM Proxy builds.",
    },
)


__all__ = [
    "V1_MODELS_PATH",
    "V1_CHAT_COMPLETIONS_PATH",
    "V1_COMPLETIONS_PATH",
    "OpenAiProxyCapability",
    "OPENAI_PROXY_CAPABILITIES",
]
