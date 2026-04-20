"""
Service orchestration helpers for WebUI routes.

Keeps ServiceStarter import/bootstrap and service actions outside route modules.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from typing import Any

import requests

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


def open_webui_status_snapshot(*, ping_timeout_sec: float = 0.6) -> dict[str, Any]:
    ss = get_service_starter()
    st = ss.status()["open_webui"]
    url = st["url"]
    status: dict[str, Any] = {"url": url, "running": bool(st.get("running"))}
    if st.get("running"):
        status["detected_by"] = "docker"
    if st.get("http_status") is not None:
        status["http_status"] = st["http_status"]
    if st.get("http_error"):
        status["http_error"] = st["http_error"]
    if status["running"]:
        try:
            resp = requests.get(url, timeout=ping_timeout_sec)
            status["http_status"] = resp.status_code
        except Exception as e:
            status["http_error"] = str(e)
    return status


def start_open_webui(*, open_webui_ollama_url_for_container: str | None = None) -> tuple[bool, str, str]:
    ss = get_service_starter()
    cfg = ss.cfg
    name = cfg.open_webui_container_name
    if open_webui_ollama_url_for_container:
        cfg = replace(
            cfg,
            open_webui_ollama_url_for_container=open_webui_ollama_url_for_container,
        )
    from servicestarter.engine import ServiceStarter

    ok, output = ServiceStarter(cfg).start_open_webui()
    return bool(ok), str(output), str(name)


def stop_open_webui() -> tuple[bool, str, str]:
    ss = get_service_starter()
    ok, output = ss.stop_open_webui()
    return bool(ok), str(output), str(ss.cfg.open_webui_container_name)


def get_open_webui_config() -> Any:
    ss = get_service_starter()
    return ss.cfg


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
    "get_open_webui_config",
    "get_service_starter",
    "open_webui_status_snapshot",
    "start_ollama",
    "start_open_webui",
    "start_qdrant",
    "stop_ollama",
    "stop_open_webui",
    "stop_qdrant",
]
