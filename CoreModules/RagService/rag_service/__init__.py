"""RAG Service: standalone retrieval, runtime helpers, and HTTP API."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag_service.core import RagCore, StepRegistry
    from rag_service.runtime import RagRuntime, RagRuntimeConfig

__all__ = ["RagCore", "RagRuntime", "RagRuntimeConfig", "StepRegistry"]


def __getattr__(name: str):
    if name in {"RagCore", "StepRegistry"}:
        from rag_service.core import RagCore, StepRegistry

        return {"RagCore": RagCore, "StepRegistry": StepRegistry}[name]
    if name in {"RagRuntime", "RagRuntimeConfig"}:
        from rag_service.runtime import RagRuntime, RagRuntimeConfig

        return {"RagRuntime": RagRuntime, "RagRuntimeConfig": RagRuntimeConfig}[name]
    raise AttributeError(name)
