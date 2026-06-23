"""
ChironAI RAG service package: consumer kinds, app-setting keys, ports, bindings, policy.
"""

from chironai_rag.bindings import ConsumerRagBindings
from chironai_rag.consumers import (
    RAG_COLLECTION_APP_SETTING,
    RagConsumer,
    app_setting_key_for_consumer,
)
from chironai_rag.policy import (
    RAG_PROJECT_ENABLED_APP_SETTING,
    AppSettingsRagProjectPolicy,
    PermissiveRagProjectPolicy,
    RagProjectPolicy,
)
from chironai_rag.ports import AppSettingsPort

__all__ = [
    "AppSettingsPort",
    "AppSettingsRagProjectPolicy",
    "ConsumerRagBindings",
    "PermissiveRagProjectPolicy",
    "RAG_COLLECTION_APP_SETTING",
    "RAG_PROJECT_ENABLED_APP_SETTING",
    "RagConsumer",
    "RagProjectPolicy",
    "app_setting_key_for_consumer",
]
