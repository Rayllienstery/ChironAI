"""
Chat LLM client port.

Abstract interface for chat/completion API.
Implementations (e.g. Ollama /api/chat) live in infrastructure.
"""

from __future__ import annotations

from typing import Any, Protocol


class ChatLLMClient(Protocol):
    """Port for chat/completion calls to an LLM."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        stream: bool = False,
        options: dict[str, Any] | None = None,
    ) -> str:
        """
        Send messages and return the assistant reply as a string.
        options: generation options (num_predict, temperature, etc.).
        Raises domain errors on failure.
        """
        ...


__all__ = ["ChatLLMClient"]
