"""LLM Proxy Core Module — OpenAI-shaped HTTP surface with injectable wiring."""

from __future__ import annotations

from llm_proxy.config import LlmProxyRuntimeConfig, RAG_MODEL_ID
from llm_proxy.contracts import LlmProxyBaseContext, LlmProxyExternalDocsBundle, LlmProxyWiring
from llm_proxy.v1_blueprint import create_v1_blueprint

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "RAG_MODEL_ID",
    "LlmProxyRuntimeConfig",
    "LlmProxyBaseContext",
    "LlmProxyExternalDocsBundle",
    "LlmProxyWiring",
    "create_v1_blueprint",
]
