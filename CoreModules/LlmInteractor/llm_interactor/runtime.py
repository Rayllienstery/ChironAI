"""Provider registry and blind request runtime."""

from __future__ import annotations

from collections.abc import Iterator

from llm_interactor.contracts import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ModelDescriptor,
    ProviderDescriptor,
    ProviderHealth,
)


class ProviderRegistry:
    """Mutable in-process provider registry."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        desc = provider.describe()
        if desc.id in self._providers:
            raise ValueError(f"duplicate provider id: {desc.id}")
        self._providers[desc.id] = provider

    def get(self, provider_id: str) -> LLMProvider | None:
        return self._providers.get(provider_id)

    def providers(self) -> list[LLMProvider]:
        return list(self._providers.values())

    def descriptors(self) -> list[ProviderDescriptor]:
        return [provider.describe() for provider in self._providers.values()]

    def list_models(self) -> list[ModelDescriptor]:
        out: list[ModelDescriptor] = []
        for provider in self._providers.values():
            out.extend(provider.list_models())
        return out

    def healths(self) -> list[ProviderHealth]:
        return [provider.health_check() for provider in self._providers.values()]


class LLMRuntime:
    """Blind runtime that dispatches normalized requests to registered providers."""

    def __init__(self, registry: ProviderRegistry, *, default_provider_id: str | None = None) -> None:
        self._registry = registry
        self._default_provider_id = default_provider_id

    def _resolve_provider(self, request: LLMRequest) -> LLMProvider:
        provider_id = (request.provider_id or self._default_provider_id or "").strip()
        if not provider_id:
            raise RuntimeError("no provider configured")
        provider = self._registry.get(provider_id)
        if provider is None:
            raise RuntimeError(f"provider not found: {provider_id}")
        return provider

    def invoke(self, request: LLMRequest) -> LLMResponse:
        return self._resolve_provider(request).invoke(request)

    def stream_invoke(self, request: LLMRequest) -> Iterator[LLMStreamEvent]:
        return self._resolve_provider(request).stream_invoke(request)

    @property
    def registry(self) -> ProviderRegistry:
        return self._registry
