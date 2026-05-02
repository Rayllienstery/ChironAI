"""Environment-driven configuration for ServiceStarter.

Docker CLI resolution (see docker_ops): optional ``DOCKER_EXE`` (full path to docker.exe),
else ``PATH``, else typical Docker Desktop path on Windows
(``ProgramFiles\\Docker\\Docker\\resources\\bin\\docker.exe``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


def _ollama_listen_from_base(base_url: str, default_host: str) -> str:
    base_url = (base_url or "").rstrip("/")
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    host = parsed.hostname or default_host
    port = parsed.port
    if port is None:
        port = 11343
    return f"{host}:{port}"


@dataclass(frozen=True)
class ServiceStarterConfig:
    """Runtime configuration (immutable)."""

    ollama_base_url: str
    """Base URL for Ollama HTTP API (no trailing path), e.g. http://localhost:11343."""

    ollama_listen: str
    """Value for OLLAMA_HOST when starting `ollama serve`, e.g. 127.0.0.1:11343."""

    qdrant_http_url: str
    qdrant_container_name: str
    qdrant_image: str
    qdrant_host_http_port: int
    qdrant_host_grpc_port: int

    docker_desktop_installer_url: str
    ollama_installer_url: str

    docker_desktop_exe: str
    """Path to Docker Desktop executable used for best-effort start on Windows."""

    docker_ready_timeout_sec: float
    docker_poll_interval_sec: float
    http_wait_timeout_sec: float

    @classmethod
    def from_env(cls) -> ServiceStarterConfig:
        ollama_port = int(os.getenv("OLLAMA_PORT", "11343"))
        ollama_listen_host = os.getenv("OLLAMA_LISTEN_HOST", "127.0.0.1")
        default_base = f"http://{ollama_listen_host}:{ollama_port}"
        ollama_base = (os.getenv("OLLAMA_BASE_URL") or default_base).rstrip("/")

        listen = os.getenv("OLLAMA_HOST_VALUE")
        if not listen:
            listen = f"{ollama_listen_host}:{ollama_port}"

        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
        q_http_port = int(os.getenv("QDRANT_HOST_HTTP_PORT", "6333"))
        q_grpc_port = int(os.getenv("QDRANT_HOST_GRPC_PORT", "6334"))

        return cls(
            ollama_base_url=ollama_base,
            ollama_listen=listen,
            qdrant_http_url=qdrant_url,
            qdrant_container_name=os.getenv("QDRANT_CONTAINER_NAME", "qdrant"),
            qdrant_image=os.getenv("QDRANT_IMAGE", "qdrant/qdrant:latest"),
            qdrant_host_http_port=q_http_port,
            qdrant_host_grpc_port=q_grpc_port,
            docker_desktop_installer_url=os.getenv(
                "DOCKER_DESKTOP_INSTALLER_URL",
                "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe",
            ),
            ollama_installer_url=os.getenv(
                "OLLAMA_INSTALLER_URL",
                "https://ollama.com/download/OllamaSetup.exe",
            ),
            docker_desktop_exe=os.getenv(
                "DOCKER_DESKTOP_EXE",
                r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
            ),
            docker_ready_timeout_sec=float(os.getenv("SERVICESTARTER_DOCKER_READY_TIMEOUT", "120")),
            docker_poll_interval_sec=float(os.getenv("SERVICESTARTER_DOCKER_POLL_INTERVAL", "5")),
            http_wait_timeout_sec=float(os.getenv("SERVICESTARTER_HTTP_WAIT_TIMEOUT", "60")),
        )
