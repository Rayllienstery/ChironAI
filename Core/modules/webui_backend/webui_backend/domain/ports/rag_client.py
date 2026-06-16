"""Port: call rag_service via HTTP (core/contracts/rag_api)."""

from __future__ import annotations

from typing import Any, Protocol


class RagClient(Protocol):
    """Port for RAG service (health, chat completions)."""

    def health(self) -> dict[str, Any]:
        """GET /health."""
        ...

    def chat_completions(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/chat/completions. Returns JSON response."""
        ...


__all__ = ["RagClient"]
