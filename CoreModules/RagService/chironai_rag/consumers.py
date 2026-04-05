"""Which WebUI/runtime consumer uses which persisted collection setting."""

from __future__ import annotations

from enum import Enum

__all__ = [
    "RagConsumer",
    "RAG_COLLECTION_APP_SETTING",
    "CLAWCODE_RAG_COLLECTION_APP_SETTING",
    "app_setting_key_for_consumer",
]


class RagConsumer(str, Enum):
    """Logical RAG consumer in the monorepo (maps to app_settings keys)."""

    LLM_PROXY = "llm_proxy"
    CLAWCODE = "clawcode"


# Stable keys used in infrastructure.database settings / app_settings.
RAG_COLLECTION_APP_SETTING = "rag_collection"
CLAWCODE_RAG_COLLECTION_APP_SETTING = "clawcode_rag_collection"


def app_setting_key_for_consumer(consumer: RagConsumer) -> str:
    if consumer == RagConsumer.LLM_PROXY:
        return RAG_COLLECTION_APP_SETTING
    if consumer == RagConsumer.CLAWCODE:
        return CLAWCODE_RAG_COLLECTION_APP_SETTING
    raise ValueError(f"unknown consumer: {consumer!r}")
