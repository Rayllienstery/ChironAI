"""Compatibility wrapper for the extension registry client.

The registry implementation is owned by ``Core/modules/extensions_backend``.
"""

from __future__ import annotations

try:
    from extensions_backend.registry_client import (
        ExtensionRegistryClient,
        ExtensionRegistryDiagnostic,
        ExtensionRegistryLoadResult,
    )
except Exception:  # pragma: no cover - extension workers do not need registry loading
    ExtensionRegistryDiagnostic = None  # type: ignore[assignment]
    ExtensionRegistryLoadResult = None  # type: ignore[assignment]

    class ExtensionRegistryClient:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("ExtensionRegistryClient is owned by extensions_backend and is unavailable")

__all__ = ["ExtensionRegistryClient", "ExtensionRegistryDiagnostic", "ExtensionRegistryLoadResult"]
