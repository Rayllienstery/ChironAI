"""Compose extensions_backend with llm_interactor for host runtime bootstrap."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_log = logging.getLogger(__name__)

DEFAULT_LLM_PROVIDER_ID = "ollama"


@dataclass(frozen=True)
class ExtensionHostStack:
    """Wired extension-management service and runtime handles for the app host."""

    service: Any
    manager: Any
    runtime: Any | None
    provider_registry: Any | None
    default_provider_id: str


def build_extension_host_stack(
    *,
    project_root: Path | str,
    settings_repo: Any,
    chat_client: Any | None = None,
    docker_runtime: Any | None = None,
    host_metadata: dict[str, Any] | None = None,
    default_provider_id: str = DEFAULT_LLM_PROVIDER_ID,
    bootstrap_sync: bool = True,
    registry_url: str | None = None,
    blocklist_url: str | None = None,
    github_token: str | None = None,
    get_settings_repository: Callable[[], Any] | None = None,
) -> ExtensionHostStack | None:
    """
    Build the extension host stack (management service + optional runtime bootstrap).

    Returns ``None`` when extension modules are unavailable; callers fall back to
    direct chat clients without provider extensions.
    """
    try:
        from extensions_backend import (
            ExtensionBlocklistPolicy,
            ExtensionManagementService,
            ExtensionRegistryClient,
            GitHubExtensionRepositoryClient,
        )
        from llm_interactor import ExtensionManager, ProviderHostContext
    except Exception as exc:
        _log.warning("Extension host modules unavailable: %s", exc)
        return None

    root = Path(project_root).resolve()
    settings_getter = get_settings_repository or (lambda: settings_repo)

    if docker_runtime is None:
        try:
            from docker_manager import DockerManager

            docker_runtime = DockerManager()
        except Exception as exc:
            _log.warning("DockerManager unavailable for extension host: %s", exc)
            docker_runtime = None

    if registry_url is None or blocklist_url is None or github_token is None:
        try:
            from config import (
                get_extensions_blocklist_url,
                get_extensions_registry_url,
                get_github_token,
            )

            registry_url = registry_url if registry_url is not None else (get_extensions_registry_url() or None)
            blocklist_url = blocklist_url if blocklist_url is not None else (get_extensions_blocklist_url() or None)
            github_token = github_token if github_token is not None else (get_github_token() or None)
        except Exception as exc:
            _log.warning("Extension registry config unavailable: %s", exc)
            registry_url = registry_url or None
            blocklist_url = blocklist_url or None
            github_token = github_token or None

    metadata = dict(host_metadata or {})
    metadata.setdefault("source", "extensions_host.wiring")
    try:
        from config import get_default_embed_model, get_default_rerank_model, get_ollama_base_url, get_ollama_chat_url

        metadata.update(
            {
                "base_url": get_ollama_base_url(),
                "chat_url": get_ollama_chat_url(),
                "embed_model": get_default_embed_model(),
                "rerank_model": get_default_rerank_model(),
            }
        )
    except Exception as exc:
        _log.warning("Provider host metadata unavailable: %s", exc)

    host_context = ProviderHostContext(
        project_root=str(root),
        get_settings_repository=settings_getter,
        chat_client=chat_client,
        docker_runtime=docker_runtime,
        metadata=metadata,
    )
    manager = ExtensionManager(
        project_root=root,
        host_context=host_context,
        settings_repo=settings_repo,
        registry_client=ExtensionRegistryClient(registry_url, project_root=root),
        blocklist_policy=ExtensionBlocklistPolicy(blocklist_url, project_root=root),
        repository_client=GitHubExtensionRepositoryClient(token=github_token or None),
        default_provider_id=default_provider_id,
    )
    service = ExtensionManagementService(manager, docker_manager=docker_runtime)
    runtime = None
    provider_registry = None
    if bootstrap_sync:
        try:
            service.bootstrap_runtime()
            runtime = service.runtime
            provider_registry = service.registry
            _log.info("Extension host bootstrap complete (status=%s)", service.runtime_status)
        except Exception as exc:
            err = str(getattr(service, "runtime_error", "") or exc)
            _log.warning("Extension host bootstrap failed: %s", err)

    return ExtensionHostStack(
        service=service,
        manager=manager,
        runtime=runtime,
        provider_registry=provider_registry,
        default_provider_id=default_provider_id,
    )


__all__ = [
    "DEFAULT_LLM_PROVIDER_ID",
    "ExtensionHostStack",
    "build_extension_host_stack",
]
