"""
Service orchestration helpers for WebUI routes.

Keeps service actions outside route modules.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def ensure_rag_runtime_on_path() -> None:
    """Best-effort: add Qdrant runtime dependencies to sys.path for source checkout runs."""
    for candidate in (
        os.path.join(_ROOT, "CoreModules", "DockerManager"),
        os.path.join(_ROOT, "CoreModules", "RagService"),
    ):
        if os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)


def get_rag_runtime():
    """Load RagRuntime with source-checkout fallback path."""
    try:
        from rag_service.runtime import RagRuntime
    except ModuleNotFoundError:
        ensure_rag_runtime_on_path()
        from rag_service.runtime import RagRuntime
    return RagRuntime()


def start_qdrant() -> tuple[bool, str, str]:
    runtime = get_rag_runtime()
    ok, output = runtime.start_qdrant()
    return bool(ok), str(output), str(runtime.cfg.qdrant_container_name)


def stop_qdrant() -> tuple[bool, str, str]:
    runtime = get_rag_runtime()
    ok, output = runtime.stop_qdrant()
    return bool(ok), str(output), str(runtime.cfg.qdrant_container_name)


__all__ = [
    "ensure_rag_runtime_on_path",
    "get_rag_runtime",
    "start_qdrant",
    "stop_qdrant",
]
