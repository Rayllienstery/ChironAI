"""Resolve and persist per-consumer stored collection names via AppSettingsPort."""

from __future__ import annotations

from chironai_rag.consumers import RagConsumer, app_setting_key_for_consumer
from chironai_rag.policy import PermissiveRagProjectPolicy, RagProjectPolicy
from chironai_rag.ports import AppSettingsPort

__all__ = ["ConsumerRagBindings"]


class ConsumerRagBindings:
    """
    Facade over app_settings for LLM Proxy vs ClawCode collection overrides.

    Policy hook: when ``policy.is_rag_enabled()`` is False, ``get_stored_collection`` returns
    empty string (callers treat as unset / use config default). Persistence still allowed so
    UI can save choices before a global kill-switch is flipped on.
    """

    def __init__(
        self,
        settings: AppSettingsPort,
        policy: RagProjectPolicy | None = None,
    ) -> None:
        self._settings = settings
        self._policy = policy or PermissiveRagProjectPolicy()

    def get_stored_collection(self, consumer: RagConsumer) -> str:
        if not self._policy.is_rag_enabled():
            return ""
        key = app_setting_key_for_consumer(consumer)
        return (self._settings.get_app_setting(key) or "").strip()

    def set_stored_collection(self, consumer: RagConsumer, collection_name: str) -> None:
        key = app_setting_key_for_consumer(consumer)
        self._settings.set_app_setting(key, (collection_name or "").strip())
