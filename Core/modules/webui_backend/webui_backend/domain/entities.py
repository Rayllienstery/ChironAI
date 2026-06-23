"""Domain entities for WebUI backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DashboardStats:
    """Aggregated stats for dashboard (from RAG, crawler, ingestion)."""

    rag_status: str = ""
    crawler_status: str = ""
    last_request_seconds: float | None = None
    last_request_tokens: int | None = None
    extra: dict[str, Any] | None = None


@dataclass
class UiSettings:
    """UI settings (model, prompt name, etc.)."""

    model: str = ""
    prompt_name: str = ""
    extra: dict[str, Any] | None = None


@dataclass
class LogEntry:
    """Single log entry for UI."""

    id: str = ""
    level: str = ""
    message: str = ""
    source: str = ""
    created_at: str = ""
    metadata: dict[str, Any] | None = None


__all__ = ["DashboardStats", "UiSettings", "LogEntry"]
