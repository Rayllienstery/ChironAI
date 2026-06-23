"""Provider catalog and sandbox diagnostics helpers for ExtensionManager."""

from __future__ import annotations

from typing import Any, Callable

from llm_interactor.discovery import FailedExtension, LoadedExtension
from llm_interactor.runtime import LLMRuntime


def sandbox_diagnostics(
    loaded: LoadedExtension | None,
    failed: FailedExtension | None = None,
) -> dict[str, Any]:
    provider = loaded.provider if loaded is not None else None
    sandboxed = bool(getattr(loaded, "sandboxed", False)) if loaded is not None else bool(failed and failed.sandbox_status)
    sandbox_status = (
        str(getattr(provider, "sandbox_status", "") or getattr(loaded, "sandbox_status", ""))
        if loaded is not None
        else str(failed.sandbox_status if failed is not None else "")
    )
    sandbox_error = (
        str(
            getattr(provider, "sandbox_last_error", "")
            or getattr(provider, "sandbox_error", "")
            or getattr(loaded, "sandbox_error", "")
        )
        if loaded is not None
        else str(failed.sandbox_error if failed is not None else "")
    )
    sandbox_pid = getattr(provider, "sandbox_pid", None) if provider is not None else None
    sandbox_restart_count = int(getattr(provider, "sandbox_restart_count", 0) or 0) if provider is not None else 0
    sandbox_blocked = bool(getattr(provider, "sandbox_blocked", False)) if provider is not None else False
    manual_required = (
        bool(getattr(provider, "sandbox_manual_restart_required", False))
        if provider is not None
        else sandbox_status in {"blocked", "manual_stop"}
    )
    return {
        "sandboxed": sandboxed,
        "sandbox_pid": sandbox_pid,
        "sandbox_status": sandbox_status,
        "sandbox_error": sandbox_error,
        "sandbox_last_error": sandbox_error,
        "sandbox_restart_count": sandbox_restart_count,
        "sandbox_blocked": sandbox_blocked,
        "sandbox_manual_restart_required": manual_required,
        "sandbox_can_restart": bool(loaded is not None and sandboxed),
        "sandbox_can_kill": bool(loaded is not None and sandboxed and sandbox_pid is not None),
    }


def provider_rows_from_runtime(
    runtime: LLMRuntime | None,
    *,
    asset_url: Callable[[str, str], str],
) -> list[dict[str, Any]]:
    rt = runtime
    rows: list[dict[str, Any]] = []
    if rt is not None:
        healths = {}
        for provider in rt.registry.providers():
            try:
                health = provider.health_check()
                healths[health.provider_id] = health
            except Exception:
                continue
        models_by_provider: dict[str, list[dict[str, Any]]] = {}
        descriptors = []
        for provider in rt.registry.providers():
            try:
                desc = provider.describe()
                descriptors.append(desc)
                for model in provider.list_models():
                    models_by_provider.setdefault(model.provider_id, []).append(
                        {
                            "id": model.id,
                            "label": model.label,
                            "description": model.description,
                            "metadata": dict(model.metadata or {}),
                        }
                    )
            except Exception:
                continue
        for desc in descriptors:
            health = healths.get(desc.id)
            rows.append(
                {
                    "provider_id": desc.id,
                    "extension_id": desc.extension_id,
                    "title": desc.title,
                    "description": desc.description,
                    "icon": desc.icon,
                    "icon_url": asset_url(desc.extension_id, desc.icon),
                    "capabilities": desc.capabilities.__dict__,
                    "metadata": dict(desc.metadata or {}),
                    "health": {
                        "ok": bool(health.ok) if health else False,
                        "status": health.status if health else "unknown",
                        "message": health.message if health else "",
                        "details": dict(health.details or {}) if health else {},
                    },
                    "models": models_by_provider.get(desc.id, []),
                }
            )
    return rows


def build_provider_catalog(
    rows: list[dict[str, Any]],
    *,
    capability: str | None = None,
) -> dict[str, Any]:
    cap = str(capability or "").strip().lower()
    filtered = rows
    if cap:
        filtered = [
            row
            for row in rows
            if bool((row.get("capabilities") or {}).get(cap))
        ]
    flat_models: list[dict[str, Any]] = []
    for row in filtered:
        for model in row.get("models") or []:
            flat_models.append(
                {
                    "provider_id": row.get("provider_id"),
                    "provider_title": row.get("title"),
                    "provider_icon_url": row.get("icon_url"),
                    "extension_id": row.get("extension_id"),
                    "id": model.get("id"),
                    "name": model.get("label") or model.get("id"),
                    "label": model.get("label") or model.get("id"),
                    "description": model.get("description") or "",
                    "metadata": dict(model.get("metadata") or {}),
                }
            )
    return {"providers": filtered, "models": flat_models}
