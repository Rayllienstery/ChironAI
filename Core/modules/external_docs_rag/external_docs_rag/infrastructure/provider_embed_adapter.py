"""
Embedding adapter implementing EmbeddingPort for the external-docs ingest CLI.

Requires the extension-backed LLM runtime (ollama-provider or another default provider).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_RAG_SVC = _ROOT / "CoreModules" / "RagService"
if _RAG_SVC.is_dir() and str(_RAG_SVC) not in sys.path:
    sys.path.insert(0, str(_RAG_SVC))

from rag_service.infrastructure.provider_runtime import RuntimeBackedEmbeddingProvider
from rag_service.infrastructure.runtime_hooks import get_llm_runtime

try:
    from config import get_default_embed_model
except ImportError:
    get_default_embed_model = lambda: (os.getenv("RAG_EMBED_MODEL") or "").strip()  # type: ignore[assignment]

DEFAULT_PROVIDER_ID = (os.getenv("DEFAULT_LLM_PROVIDER_ID") or "ollama").strip() or "ollama"


def _bootstrap_cli_runtime() -> object:
    from extensions_host import build_extension_host_stack

    try:
        from infrastructure.database import get_settings_repository
    except ImportError as exc:
        raise RuntimeError(
            "External-docs ingest requires ChironAI config/database modules to bootstrap the LLM runtime."
        ) from exc

    settings_repo = get_settings_repository()
    stack = build_extension_host_stack(
        project_root=str(_ROOT),
        settings_repo=settings_repo,
        chat_client=None,
        docker_runtime=None,
        host_metadata={"source": "external_docs_rag.cli"},
        get_settings_repository=get_settings_repository,
        default_provider_id=DEFAULT_PROVIDER_ID,
        bootstrap_sync=True,
    )
    if stack is None or stack.runtime is None:
        raise RuntimeError("Failed to bootstrap LLM runtime for external-docs ingest.")
    return stack.runtime


def _resolve_runtime() -> object:
    runtime = get_llm_runtime()
    if runtime is not None:
        return runtime
    return _bootstrap_cli_runtime()


class ProviderEmbedAdapter:
    """EmbeddingPort implementation via the extension LLM runtime."""

    def __init__(self, model: str | None = None, provider_id: str | None = None) -> None:
        resolved_model = (model or "").strip() or get_default_embed_model() or (os.getenv("RAG_EMBED_MODEL") or "").strip()
        self._inner = RuntimeBackedEmbeddingProvider(
            runtime_getter=_resolve_runtime,
            provider_id=(provider_id or DEFAULT_PROVIDER_ID).strip() or DEFAULT_PROVIDER_ID,
            model=resolved_model,
        )

    def embed(self, text: str) -> list[float]:
        return self._inner.embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed_batch(texts)


__all__ = ["ProviderEmbedAdapter"]
