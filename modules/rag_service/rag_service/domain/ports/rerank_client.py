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
        """
        Send prompt to rerank LLM and return raw response (e.g. JSON array string).
        Returns None on failure (caller keeps original order).
        """
        ...


__all__ = ["RerankClient"]
