"""Runtime defaults for the LLM proxy module (env-overridable)."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Logical model id for inline/code completion (no RAG); maps to configured Ollama tag in WebUI
AUTOCOMPLETE_MODEL_ID = "ChironAI-Autocomplete"


@dataclass(frozen=True)
class LlmProxyRuntimeConfig:
    """Values owned by the module; override via environment where noted."""

    autocomplete_model_logical_id: str = AUTOCOMPLETE_MODEL_ID

    @classmethod
    def from_env(cls) -> LlmProxyRuntimeConfig:
        ac_id = os.getenv("LLM_PROXY_AUTOCOMPLETE_MODEL_ID", AUTOCOMPLETE_MODEL_ID).strip() or AUTOCOMPLETE_MODEL_ID
        return cls(autocomplete_model_logical_id=ac_id)
