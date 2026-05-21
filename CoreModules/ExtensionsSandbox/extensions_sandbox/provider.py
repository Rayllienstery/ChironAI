"""LLMProvider proxy backed by an extension worker process."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from extensions_sandbox.client import ExtensionWorkerClient
from llm_interactor.contracts import (
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ModelDescriptor,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderHealth,
)


def _capabilities(raw: Any) -> ProviderCapabilities:
    return ProviderCapabilities(**dict(raw or {})) if isinstance(raw, dict) else ProviderCapabilities()


def _descriptor(raw: dict[str, Any]) -> ProviderDescriptor:
    data = dict(raw or {})
    data["capabilities"] = _capabilities(data.get("capabilities"))
    return ProviderDescriptor(**data)


def _model(raw: dict[str, Any]) -> ModelDescriptor:
    data = dict(raw or {})
    data["capabilities"] = _capabilities(data.get("capabilities"))
    return ModelDescriptor(**data)


def _health(raw: dict[str, Any]) -> ProviderHealth:
    return ProviderHealth(**dict(raw or {}))


def _response(raw: dict[str, Any]) -> LLMResponse:
    return LLMResponse(**dict(raw or {}))


def _event(raw: dict[str, Any]) -> LLMStreamEvent:
    return LLMStreamEvent(**dict(raw or {}))


class SandboxedExtensionProvider:
    """Provider proxy that forwards all extension calls to a worker process."""

    sandboxed = True

    def __init__(self, client: ExtensionWorkerClient, *, extension_id: str) -> None:
        self._client = client
        self._extension_id = extension_id

    @property
    def sandbox_status(self) -> str:
        return self._client.status

    @property
    def sandbox_error(self) -> str:
        return self._client.error

    @property
    def sandbox_pid(self) -> int | None:
        return self._client.pid

    @property
    def sandbox_last_error(self) -> str:
        return self._client.last_error

    @property
    def sandbox_restart_count(self) -> int:
        return self._client.restart_count

    @property
    def sandbox_blocked(self) -> bool:
        return self._client.blocked

    @property
    def sandbox_manual_restart_required(self) -> bool:
        return self._client.manual_restart_required

    def close(self) -> None:
        self._client.close()

    def restart_sandbox(self) -> None:
        self._client.restart()

    def kill_sandbox(self) -> None:
        self._client.kill()

    def describe(self) -> ProviderDescriptor:
        return _descriptor(self._client.call("describe", timeout_sec=5.0))

    def list_models(self) -> list[ModelDescriptor]:
        return [_model(item) for item in self._client.call("list_models", timeout_sec=8.0)]

    def health_check(self) -> ProviderHealth:
        return _health(self._client.call("health_check", timeout_sec=5.0))

    def invoke(self, request: LLMRequest) -> LLMResponse:
        return _response(self._client.call("invoke", {"request": request}, timeout_sec=900.0))

    def stream_invoke(self, request: LLMRequest) -> Iterator[LLMStreamEvent]:
        for item in self._client.call("stream_invoke", {"request": request}, timeout_sec=900.0):
            yield _event(item)

    def get_tab_descriptor(self, *, runtime: Any | None = None) -> dict[str, Any]:
        return dict(self._client.call("get_tab_descriptor", timeout_sec=5.0) or {})

    def get_tab_payload(self, *, runtime: Any | None = None) -> dict[str, Any]:
        return dict(self._client.call("get_tab_payload", timeout_sec=8.0) or {})

    def run_action(self, action_id: str, payload: dict[str, Any], *, runtime: Any | None = None) -> dict[str, Any]:
        result = self._client.call(
            "run_action",
            {"action_id": str(action_id or ""), "payload": dict(payload or {})},
            timeout_sec=900.0,
        )
        return dict(result or {}) if isinstance(result, dict) else {"ok": True, "result": result}


def start_sandboxed_extension_provider(
    *,
    source_dir: Path,
    entrypoint: str,
    manifest: Any,
    host_context: Any,
) -> SandboxedExtensionProvider:
    client = ExtensionWorkerClient(
        source_dir=source_dir,
        entrypoint=entrypoint,
        manifest=manifest,
        project_root=getattr(host_context, "project_root"),
        host_context=host_context,
    )
    return SandboxedExtensionProvider(client, extension_id=str(getattr(manifest, "id", source_dir.name)))
