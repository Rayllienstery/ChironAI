"""Implementation-free Docker runtime contracts shared across modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


def _str_list() -> list[str]:
    return []


def _str_dict() -> dict[str, str]:
    return {}


def _any_dict() -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class DockerContainerSpec:
    """Declarative container spec for extension and service-owned containers."""

    name: str
    image: str
    ports: list[str] = field(default_factory=_str_list)
    env: dict[str, str] = field(default_factory=_str_dict)
    volumes: list[str] = field(default_factory=_str_list)
    restart: str = "unless-stopped"
    extra_hosts: list[str] = field(default_factory=_str_list)
    command: list[str] = field(default_factory=_str_list)
    labels: dict[str, str] = field(default_factory=_str_dict)


@dataclass(frozen=True)
class DockerContainerState:
    exists: bool
    running: bool = False
    name: str = ""
    image: str = ""
    env: dict[str, str] = field(default_factory=_str_dict)
    ports: dict[str, Any] = field(default_factory=_any_dict)
    volumes: list[str] = field(default_factory=_str_list)
    labels: dict[str, str] = field(default_factory=_str_dict)


class DockerRuntime(Protocol):
    """Host capability surface exposed to extensions and service orchestrators."""

    def ensure_container(self, spec: DockerContainerSpec) -> dict[str, Any]: ...

    def stop_container(self, name: str) -> dict[str, Any]: ...

    def inspect_container(self, name: str) -> dict[str, Any]: ...

    def wait_http(self, url: str, *, timeout: float = 60.0, interval: float = 2.0) -> dict[str, Any]: ...

    def check_image_update(self, image: str) -> dict[str, Any]: ...


__all__ = ["DockerContainerSpec", "DockerContainerState", "DockerRuntime"]
