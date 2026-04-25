"""Blind LLM runtime and extension management."""

from llm_interactor.compat import RuntimeBackedChatClient
from llm_interactor.contracts import (
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
from llm_interactor.discovery import FailedExtension, LoadedExtension
from llm_interactor.install_state import ExtensionsRepository, InstalledExtensionRecord
from llm_interactor.manager import ExtensionManager, RuntimeBootstrap
from llm_interactor.manifest import (
    ALLOWED_UI_COMPONENT_TYPES,
    EXTENSION_API_VERSION,
    EXTENSION_TYPE_LLM_PROVIDER,
    BackendManifest,
    ExtensionManifest,
)
from llm_interactor.registry_client import ExtensionRegistryClient
from llm_interactor.runtime import LLMRuntime, ProviderRegistry

__all__ = [
    "ALLOWED_UI_COMPONENT_TYPES",
    "BackendManifest",
    "EXTENSION_API_VERSION",
    "EXTENSION_TYPE_LLM_PROVIDER",
    "ExtensionManager",
    "ExtensionManifest",
    "ExtensionRegistryClient",
    "ExtensionsRepository",
    "FailedExtension",
    "InstalledExtensionRecord",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMRuntime",
    "LLMStreamEvent",
    "LoadedExtension",
    "MessagePart",
    "ModelDescriptor",
    "ProviderCapabilities",
    "ProviderDescriptor",
    "ProviderHealth",
    "ProviderHostContext",
    "ProviderRegistry",
    "RuntimeBackedChatClient",
    "RuntimeBootstrap",
    "ToolSpec",
]
