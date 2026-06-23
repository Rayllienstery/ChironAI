"""Compatibility facade for shared LLM runtime contracts."""

from core.contracts.llm_runtime import (
    DockerContainerSpec,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    MessagePart,
    ModelDescriptor,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderHealth,
    ProviderHostContext,
    ToolSpec,
)

__all__ = [
    "DockerContainerSpec",
    "MessagePart",
    "ToolSpec",
    "ProviderCapabilities",
    "ModelDescriptor",
    "ProviderDescriptor",
    "ProviderHealth",
    "LLMRequest",
    "LLMResponse",
    "LLMStreamEvent",
    "ProviderHostContext",
    "LLMProvider",
]
