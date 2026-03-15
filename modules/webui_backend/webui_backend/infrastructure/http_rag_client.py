"""RagClient implementation via HTTP to rag_service."""

from __future__ import annotations

import os
from typing import Any

import requests

from webui_backend.domain.ports import RagClient

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:5001")


class HttpRagClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or RAG_SERVICE_URL).rstrip("/")

    def health(self) -> dict[str, Any]:
        r = requests.get(f"{self._base}/health", timeout=5)
        r.raise_for_status()
        return r.json()

    def chat_completions(self, body: dict[str, Any]) -> dict[str, Any]:
        r = requests.post(f"{self._base}/v1/chat/completions", json=body, timeout=600)
        r.raise_for_status()
        return r.json()


__all__ = ["HttpRagClient"]
