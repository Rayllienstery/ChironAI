"""Compatibility wrapper to standalone rag_service params."""

from __future__ import annotations

from rag_service.application.params import (
    RAGAnswerParams,
    RAGDependencies,
    get_rag_answer_params as _get_rag_answer_params_impl,
)


def get_rag_answer_params(
    *,
    webui_dir: str | None = None,
    collection_name: str | None = None,
    prompt_name: str | None = None,
) -> tuple[RAGAnswerParams, RAGDependencies]:
    """
    Backward-compatible adapter.

    ``prompt_name`` is accepted for legacy call sites but ignored by isolated rag_service.
    """
    _ = prompt_name
    return _get_rag_answer_params_impl(
        webui_dir=webui_dir,
        collection_name=collection_name,
    )


__all__ = ["RAGAnswerParams", "RAGDependencies", "get_rag_answer_params"]
