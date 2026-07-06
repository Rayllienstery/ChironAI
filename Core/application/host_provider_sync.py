"""Register custom OpenAI-compatible providers into the shared LLM runtime registry."""

from __future__ import annotations

from typing import Any

from application.custom_openai_providers import load_custom_openai_provider_records
from application.openai_compatible_provider import OpenAICompatibleProvider


def _is_custom_provider(provider: Any) -> bool:
    try:
        metadata = provider.describe().metadata or {}
    except Exception:
        return False
    return str(metadata.get("source") or "") == "custom_openai"


def sync_custom_openai_providers(registry: Any, settings_repo: Any) -> list[str]:
    """Replace host-managed custom providers in ``registry`` from app settings."""
    records = [
        dict(record)
        for record in load_custom_openai_provider_records(settings_repo)
        if record.get("enabled", True) and str(record.get("api_key") or "").strip()
    ]
    desired_ids = {str(record.get("id") or "").strip().lower() for record in records}
    for provider in list(registry.providers()):
        if _is_custom_provider(provider):
            pid = str(provider.describe().id or "").strip().lower()
            if pid not in desired_ids and hasattr(registry, "unregister"):
                registry.unregister(pid)
    registered: list[str] = []
    for record in records:
        provider = OpenAICompatibleProvider(record)
        pid = provider.describe().id
        if hasattr(registry, "replace"):
            registry.replace(provider)
        else:
            if registry.get(pid) is not None and hasattr(registry, "unregister"):
                registry.unregister(pid)
            registry.register(provider)
        registered.append(pid)
    return registered
