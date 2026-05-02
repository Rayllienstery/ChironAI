"""
Service orchestration helpers for WebUI routes.

Keeps ServiceStarter import/bootstrap and service actions outside route modules.
"""

from __future__ import annotations

import os
import sys
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ensure_servicestarter_on_path() -> None:
    """Best-effort: add CoreModules/ServiceStarter to sys.path for source checkout runs."""
    candidate = os.path.join(_ROOT, "CoreModules", "ServiceStarter")
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


def get_service_starter() -> Any:
    """Load ServiceStarter with source-checkout fallback path."""
    try:
        from servicestarter.engine import ServiceStarter
    except ModuleNotFoundError:
        ensure_servicestarter_on_path()
        from servicestarter.engine import ServiceStarter
    return ServiceStarter()


def start_qdrant() -> tuple[bool, str, str]:
    ss = get_service_starter()
    ok, output = ss.start_qdrant()
    return bool(ok), str(output), str(ss.cfg.qdrant_container_name)


def stop_qdrant() -> tuple[bool, str, str]:
    ss = get_service_starter()
    ok, output = ss.stop_qdrant()
    return bool(ok), str(output), str(ss.cfg.qdrant_container_name)


def start_ollama() -> tuple[bool, str]:
    ss = get_service_starter()
    ok_i, out_i = ss.ensure_ollama_installed()
    if not ok_i:
        return False, str(out_i)
    ok, output = ss.start_ollama()
    return bool(ok), str(output)


def stop_ollama(*, base_url: str, default_port: int = 11434) -> tuple[bool, str]:
    try:
        from servicestarter.ollama_ops import ollama_port_from_base_url, stop_ollama_process
    except ModuleNotFoundError:
        ensure_servicestarter_on_path()
        from servicestarter.ollama_ops import ollama_port_from_base_url, stop_ollama_process

    port = ollama_port_from_base_url(base_url, default_port=default_port)
    ok, output = stop_ollama_process(listen_port=port)
    return bool(ok), str(output)


__all__ = [
    "ensure_servicestarter_on_path",
    "get_service_starter",
    "start_ollama",
    "start_qdrant",
    "stop_ollama",
    "stop_qdrant",
]
