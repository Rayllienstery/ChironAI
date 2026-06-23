"""
Project-level RAG policy (extension point for a future global "RAG enabled" toggle).

Default: RAG is allowed. Optional AppSettingsRagProjectPolicy reads a string app_setting;
when missing or empty, RAG is treated as enabled (backward compatible).
"""

from __future__ import annotations

from typing import Protocol

from chironai_rag.ports import AppSettingsPort

__all__ = ["RagProjectPolicy", "PermissiveRagProjectPolicy", "AppSettingsRagProjectPolicy"]

# Reserved app_settings key for a future WebUI toggle (not yet written by CoreUI).
RAG_PROJECT_ENABLED_APP_SETTING = "rag_project_enabled"


class RagProjectPolicy(Protocol):
    def is_rag_enabled(self) -> bool:
        """When False, callers may skip retrieval / refuse logical RAG model (future use)."""
        ...


class PermissiveRagProjectPolicy:
    """Always allow RAG; use until a global toggle is implemented end-to-end."""

    def is_rag_enabled(self) -> bool:
        return True


class AppSettingsRagProjectPolicy:
    """
    If setting is '0', 'false', 'no', 'off' (case-insensitive) -> disabled.
    Missing or any other value -> enabled.
    """

    def __init__(self, settings: AppSettingsPort, key: str = RAG_PROJECT_ENABLED_APP_SETTING) -> None:
        self._settings = settings
        self._key = key

    def is_rag_enabled(self) -> bool:
        raw = (self._settings.get_app_setting(self._key) or "").strip().lower()
        if not raw:
            return True
        return raw not in ("0", "false", "no", "off", "disabled")
