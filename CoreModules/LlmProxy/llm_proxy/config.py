"""Runtime defaults for the LLM proxy module (env-overridable)."""

from __future__ import annotations

import os
from dataclasses import dataclass


# Logical model id clients use for RAG-backed completions
RAG_MODEL_ID = "rag-ollama"


@dataclass(frozen=True)
class LlmProxyRuntimeConfig:
    """Values owned by the module; override via environment where noted."""

    rag_model_logical_id: str = RAG_MODEL_ID
    recent_success_ttl_s: float = 45.0
    recent_noop_ttl_s: float = 120.0

    @classmethod
    def from_env(cls) -> LlmProxyRuntimeConfig:
        return cls(
            rag_model_logical_id=os.getenv("LLM_PROXY_RAG_MODEL_ID", RAG_MODEL_ID).strip() or RAG_MODEL_ID,
            recent_success_ttl_s=float(os.getenv("LLM_PROXY_RECENT_SUCCESS_TTL_S", "45")),
            recent_noop_ttl_s=float(os.getenv("LLM_PROXY_RECENT_NOOP_TTL_S", "120")),
        )
