"""Docker helpers backed by the DockerManager CoreModule."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from docker_manager import DockerContainerSpec, DockerManager
from servicestarter.config import ServiceStarterConfig


def _manager() -> DockerManager:
    return DockerManager()


def docker_version_available() -> bool:
    return bool(_manager().status().get("cli_available"))


def docker_engine_info() -> tuple[bool, str]:
    return _manager().engine_info()


def docker_engine_ready() -> bool:
    ok, _ = docker_engine_info()
    return ok


def container_name_matches_running(filter_name: str) -> bool:
    result = _manager().containers()
    if not bool(result.get("ok")):
        return False
    for item in result.get("containers") or []:
        name = str((item or {}).get("name") or "").strip()
        if not name:
            continue
        if bool((item or {}).get("running")) and (name == filter_name or filter_name in name or name.endswith(filter_name)):
            return True
    return False


def container_exists(name: str) -> bool:
    return _manager().container_exists(name)


def container_is_running(name: str) -> bool:
    return _manager().container_running(name)


def wait_for_docker_engine(
    cfg: ServiceStarterConfig,
    *,
    start_desktop_on_windows: bool = True,
) -> tuple[bool, str]:
    return _manager().wait_engine_tuple(
        docker_desktop_exe=cfg.docker_desktop_exe,
        timeout=cfg.docker_ready_timeout_sec,
        interval=cfg.docker_poll_interval_sec,
        start_desktop_on_windows=start_desktop_on_windows,
    )


def docker_pull(image: str, *, timeout: float = 600.0) -> tuple[bool, str]:
    result = _manager().pull_image(image)
    return bool(result.get("ok")), str(result.get("message") or result.get("details") or result.get("error") or "")


def docker_start_container(name: str) -> tuple[bool, str]:
    result = _manager().start_container(name)
    msg = str(result.get("message") or result.get("details") or result.get("error") or "")
    if not bool(result.get("ok")) and "already running" in msg.lower():
        return True, "already running"
    return bool(result.get("ok")), msg


def docker_stop_container(name: str) -> tuple[bool, str]:
    result = _manager().stop_container(name)
    return bool(result.get("ok")), str(result.get("message") or result.get("details") or result.get("error") or "")


def _ollama_container_name(cfg: ServiceStarterConfig) -> str:
    explicit = (os.getenv("OLLAMA_CONTAINER_NAME") or "").strip()
    return explicit or getattr(cfg, "ollama_container_name", None) or "chironai-ollama"


def _ollama_docker_image(cfg: ServiceStarterConfig) -> str:
    explicit = (os.getenv("OLLAMA_DOCKER_IMAGE") or "").strip()
    return explicit or getattr(cfg, "ollama_docker_image", None) or "ollama/ollama:latest"


def _ollama_docker_volume(cfg: ServiceStarterConfig) -> str:
    explicit = (os.getenv("OLLAMA_DOCKER_VOLUME") or "").strip()
    return explicit or getattr(cfg, "ollama_docker_volume", None) or "ollama_models:/root/.ollama"


def _ollama_host_port(cfg: ServiceStarterConfig) -> int:
    explicit = (os.getenv("OLLAMA_PORT") or "").strip()
    if explicit:
        try:
            return int(explicit)
        except ValueError:
            pass
    parsed = urlparse(
        cfg.ollama_base_url if "://" in cfg.ollama_base_url else f"http://{cfg.ollama_base_url}"
    )
    return int(parsed.port or 11434)


def ensure_ollama_container(cfg: ServiceStarterConfig) -> tuple[bool, str]:
    """Start Ollama as a Docker container using the configured spec."""
    host_port = _ollama_host_port(cfg)
    volume = _ollama_docker_volume(cfg)
    spec = DockerContainerSpec(
        name=_ollama_container_name(cfg),
        image=_ollama_docker_image(cfg),
        ports=[f"{host_port}:11434"],
        env={"OLLAMA_HOST": "0.0.0.0:11434"},
        volumes=[volume] if volume else [],
        restart=(os.getenv("OLLAMA_DOCKER_RESTART") or "unless-stopped").strip(),
        labels={"chironai.service": "ollama"},
    )
    result = _manager().ensure_container(spec)
    return bool(result.get("ok")), str(result.get("message") or result.get("details") or result.get("error") or "")


def ensure_qdrant_container(cfg: ServiceStarterConfig) -> tuple[bool, str]:
    spec = DockerContainerSpec(
        name=cfg.qdrant_container_name,
        image=cfg.qdrant_image,
        ports=[
            f"{cfg.qdrant_host_http_port}:6333",
            f"{cfg.qdrant_host_grpc_port}:6334",
        ],
        volumes=["qdrant_storage:/qdrant/storage"],
        restart="unless-stopped",
        labels={"chironai.service": "qdrant"},
    )
    result = _manager().ensure_container(spec)
    return bool(result.get("ok")), str(result.get("message") or result.get("details") or result.get("error") or "")


def wait_for_http_json(
    url: str,
    *,
    path: str,
    ok_status: tuple[int, ...] = (200,),
    timeout_sec: float = 60.0,
    interval: float = 2.0,
) -> tuple[bool, str | None]:
    result = _manager().wait_http(
        url,
        path=path,
        ok_status=ok_status,
        timeout=timeout_sec,
        interval=interval,
    )
    return bool(result.get("ok")), None if bool(result.get("ok")) else str(result.get("error") or "timeout")


def qdrant_port_from_url(url: str) -> int:
    parsed = urlparse(url) if "://" in url else urlparse(f"http://{url}")
    return int(parsed.port or 6333)
