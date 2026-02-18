"""
Chat LLM client port.

Abstract interface for chat/completion API.
Implementations (e.g. Ollama /api/chat) live in infrastructure.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class ChatLLMClient(Protocol):
    """Port for chat/completion calls to an LLM."""

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send messages and return the assistant reply as a string.
        options: generation options (num_predict, temperature, etc.).
        Raises domain errors on failure.
        """
        ...


__all__ = ["ChatLLMClient"]
