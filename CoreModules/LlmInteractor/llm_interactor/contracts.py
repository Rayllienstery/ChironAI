"""Provider-agnostic DTOs and contracts for the blind LLM runtime."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

try:
    from docker_manager import DockerContainerSpec as _DockerContainerSpec

    DockerContainerSpec = _DockerContainerSpec
except Exception:
    DockerContainerSpec = None  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class MessagePart:
    """Normalized chat content part."""

    type: str
    text: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    """Normalized tool definition."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderCapabilities:
    """Provider capability flags for routing and UI."""

    chat: bool = True
    embed: bool = False
    rerank: bool = False
    completions: bool = False
    streaming: bool = True
    tools: bool = False
    vision: bool = False
    model_listing: bool = True
    health_check: bool = True
    tab_ui: bool = False
    service_actions: bool = False
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelDescriptor:
    """Provider model or logical model descriptor."""

    id: str
    provider_id: str
    label: str
    description: str = ""
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderDescriptor:
    """Provider metadata exposed to UI and diagnostics."""

    id: str
    extension_id: str
    title: str
    description: str = ""
    icon: str = ""
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderHealth:
    """Health information for a provider."""

    provider_id: str
    ok: bool
    status: str = "unknown"
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMRequest:
    """Normalized request envelope for runtime -> provider calls."""

    model: str
    provider_id: str | None = None
    operation: Literal[
        "chat",
        "chat_api",
        "chat_api_stream_events",
        "embed",
        "rerank",
        "generate",
        "raw_ollama",
    ] = "chat"
    messages: list[dict[str, Any]] = field(default_factory=list)
    stream: bool = False
    options: dict[str, Any] | None = None
    think: bool | str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    body: dict[str, Any] | None = None
    input_text: str | None = None
    input_texts: list[str] | None = None
    rerank_query: str | None = None
    rerank_prompt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    """Normalized provider response."""

    provider_id: str
    model: str
    text: str = ""
    raw: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMStreamEvent:
    """Normalized stream event."""

    provider_id: str
    model: str
    type: str
    data: Any


@dataclass(frozen=True)
class ProviderHostContext:
    """Host-provided context passed into extension factories."""

    project_root: Path
    get_settings_repository: Callable[[], Any]
    chat_client: Any | None = None
    docker_runtime: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    """Contract implemented by extension-provided LLM backends."""

    def describe(self) -> ProviderDescriptor: ...

    def list_models(self) -> list[ModelDescriptor]: ...

    def invoke(self, request: LLMRequest) -> LLMResponse: ...

    def stream_invoke(self, request: LLMRequest) -> Iterator[LLMStreamEvent]: ...

    def health_check(self) -> ProviderHealth: ...

    def register_http_routes(self, _blueprint: Any) -> None:
        """Optional: register extension-owned HTTP routes on the host blueprint."""
        ...
