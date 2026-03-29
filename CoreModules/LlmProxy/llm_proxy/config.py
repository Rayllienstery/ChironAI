"""Runtime defaults for the LLM proxy module (env-overridable)."""

from __future__ import annotations

import os
from dataclasses import dataclass


# Logical model id clients use for RAG-backed completions (OpenAI-compatible `model` field)
RAG_MODEL_ID = "ChironAI-Worker"

# Previous default; still accepted so existing clients do not break
RAG_MODEL_LEGACY_IDS: tuple[str, ...] = ("rag-ollama",)

# Logical model id for fast inline/code completion (no RAG); same OpenAI contract as RAG_MODEL_ID
AUTOCOMPLETE_MODEL_ID = "ChironAI-Autocomplete"


@dataclass(frozen=True)
class LlmProxyRuntimeConfig:
    """Values owned by the module; override via environment where noted."""

    rag_model_logical_id: str = RAG_MODEL_ID
    autocomplete_model_logical_id: str = AUTOCOMPLETE_MODEL_ID

    @classmethod
    def from_env(cls) -> LlmProxyRuntimeConfig:
        rag_id = os.getenv("LLM_PROXY_RAG_MODEL_ID", RAG_MODEL_ID).strip() or RAG_MODEL_ID
        ac_id = os.getenv("LLM_PROXY_AUTOCOMPLETE_MODEL_ID", AUTOCOMPLETE_MODEL_ID).strip() or AUTOCOMPLETE_MODEL_ID
        return cls(
            rag_model_logical_id=rag_id,
            autocomplete_model_logical_id=ac_id,
        )


def is_rag_logical_model_id(requested: str, runtime_rag_id: str) -> bool:
    """True if `requested` is the configured RAG logical id or a legacy alias."""
    if not requested:
        return False
    if requested == runtime_rag_id:
        return True
    if requested == RAG_MODEL_ID:
        return True
    return requested in RAG_MODEL_LEGACY_IDS


def is_rag_logical_model(requested: str) -> bool:
    """Same as `is_rag_logical_model_id` using `LlmProxyRuntimeConfig.from_env()`."""
    rt = LlmProxyRuntimeConfig.from_env()
    return is_rag_logical_model_id(requested, rt.rag_model_logical_id)
