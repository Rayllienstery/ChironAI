"""
Rerank client port.

Abstract interface for the rerank LLM call (question + candidate snippets -> order).
Implementations (e.g. Ollama generate) live in infrastructure.
"""

from __future__ import annotations

from typing import Protocol


class RerankClient(Protocol):
    """Port for calling the rerank LLM (returns raw response string for domain to parse)."""

    def rerank(self, question: str, prompt_text: str) -> str | None:
        """Send a rerank prompt to the LLM and return the raw response.

        Args:
            question: The user question being answered.
            prompt_text: The fully-rendered rerank prompt (question + candidate snippets).

        Returns:
            The raw model response (typically a JSON array string), or ``None``
            on failure. Callers should keep the original order when ``None`` is
            returned.
        """
        ...


__all__ = ["RerankClient"]
