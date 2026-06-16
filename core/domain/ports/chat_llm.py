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
        stream: bool = False,  # noqa: ARG002
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,  # noqa: ARG002
    ) -> str:
        """Send messages and return the assistant reply as a string.

        Args:
            messages: A list of message dictionaries (role, content).
            model: The name of the LLM model to use.
            stream: Whether to stream the response (not supported by this synchronous port).
            options: Generation options (num_predict, temperature, etc.).
            think: Optional reasoning/thinking configuration.

        Returns:
            The assistant's reply as a string.

        Raises:
            domain.errors.ChironError: On API or connection failure.
        """
        ...


__all__ = ["ChatLLMClient"]
