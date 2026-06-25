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

    # Container hardening context (secure-by-default).
    # Extensions may request only the minimum runtime privileges they need.
    # DockerManager applies a security floor and may reject or warn about
    # privileged / unconfined configurations.
    user: str | None = None
    read_only_root_fs: bool = True
    cap_drop: list[str] = field(default_factory=lambda: ["ALL"])
    cap_add: list[str] = field(default_factory=_str_list)
    no_new_privileges: bool = True
    seccomp_profile: str | None = None
    security_opt: list[str] = field(default_factory=_str_list)
    tmpfs: list[str] = field(default_factory=_str_list)
    privileged: bool = False


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
