"""Resolve the extension-backed LLM runtime (with optional sync bootstrap)."""

from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger("trag.rag")


def resolve_llm_runtime(
    *,
    extension_manager: Any | None = None,
    llm_runtime: Any | None = None,
    sync_bootstrap: bool = True,
) -> Any | None:
    """Return LLMRuntime when ready; optionally block on extension bootstrap."""
    if llm_runtime is not None:
        return llm_runtime

    if extension_manager is not None:
        runtime = getattr(extension_manager, "runtime", None)
        if runtime is not None:
            return runtime
        if sync_bootstrap:
            _sync_bootstrap_extension_manager(extension_manager)
            runtime = getattr(extension_manager, "runtime", None)
            if runtime is not None:
                return runtime

    try:
        from rag_service.infrastructure.runtime_hooks import get_llm_runtime

        return get_llm_runtime()
    except Exception:
        return None


def _sync_bootstrap_extension_manager(extension_manager: Any) -> None:
    status = str(getattr(extension_manager, "runtime_status", "unavailable") or "unavailable")
    if status == "ready" and getattr(extension_manager, "runtime", None) is not None:
        return
    if status == "loading":
        try:
            extension_manager.bootstrap_runtime()
            return
        except Exception as exc:
            _LOG.warning("Waiting for in-flight LLM runtime bootstrap failed: %s", exc)
            return
    if status in {"unavailable", "failed"}:
        try:
            extension_manager.bootstrap_runtime()
        except Exception as exc:
            err = str(getattr(extension_manager, "runtime_error", "") or exc)
            _LOG.warning("LLM runtime sync bootstrap failed (status=%s): %s", status, err)


def ensure_llm_runtime_for_app(app: Any) -> Any | None:
    """Ensure Flask app extension service has a runtime; sync bootstrap if needed."""
    from api.http.extensions_service_access import get_extensions_service, set_extensions_runtime

    svc = get_extensions_service(app)
    if svc is None:
        return None
    runtime = resolve_llm_runtime(extension_manager=svc, sync_bootstrap=True)
    if runtime is not None:
        set_extensions_runtime(app, runtime)
    return runtime


__all__ = ["ensure_llm_runtime_for_app", "resolve_llm_runtime"]
