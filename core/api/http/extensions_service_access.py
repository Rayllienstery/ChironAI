"""Contract-shaped accessors for the extension-management service."""

from __future__ import annotations

from typing import Any

from core.contracts.extensions_api import (
    EXTENSIONS_PROVIDER_REGISTRY_APP_KEY,
    EXTENSIONS_RUNTIME_APP_KEY,
    EXTENSIONS_SERVICE_APP_KEY,
)


def get_extensions_service(app_or_current_app: Any) -> Any | None:
    extensions = getattr(app_or_current_app, "extensions", {})
    return extensions.get(EXTENSIONS_SERVICE_APP_KEY)


def set_extensions_service(app_or_current_app: Any, service: Any) -> None:
    extensions = app_or_current_app.extensions
    extensions[EXTENSIONS_SERVICE_APP_KEY] = service


def get_extensions_runtime(app_or_current_app: Any, service: Any | None = None) -> Any | None:
    extensions = getattr(app_or_current_app, "extensions", {})
    runtime = extensions.get(EXTENSIONS_RUNTIME_APP_KEY)
    if runtime is not None:
        return runtime
    svc = service if service is not None else get_extensions_service(app_or_current_app)
    return getattr(svc, "runtime", None) if svc is not None else None


def set_extensions_runtime(app_or_current_app: Any, runtime: Any) -> None:
    app_or_current_app.extensions[EXTENSIONS_RUNTIME_APP_KEY] = runtime


def get_extensions_provider_registry(app_or_current_app: Any, service: Any | None = None) -> Any | None:
    extensions = getattr(app_or_current_app, "extensions", {})
    registry = extensions.get(EXTENSIONS_PROVIDER_REGISTRY_APP_KEY)
    if registry is not None:
        return registry
    svc = service if service is not None else get_extensions_service(app_or_current_app)
    return getattr(svc, "registry", None) if svc is not None else None


def set_extensions_provider_registry(app_or_current_app: Any, registry: Any) -> None:
    app_or_current_app.extensions[EXTENSIONS_PROVIDER_REGISTRY_APP_KEY] = registry
