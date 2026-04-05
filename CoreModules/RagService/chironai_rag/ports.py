"""Protocols for dependency injection (settings store, future Qdrant adapters)."""

from __future__ import annotations

from typing import Protocol

__all__ = ["AppSettingsPort"]


class AppSettingsPort(Protocol):
    """Minimal read/write surface used by consumer RAG bindings (e.g. SQLite app_settings)."""

    def get_app_setting(self, key: str) -> str | None:
        ...

    def set_app_setting(self, key: str, value: str) -> None:
        ...
