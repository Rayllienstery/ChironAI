"""Background Qdrant health monitor with reactive Docker container events."""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from typing import Any, Callable

import requests

from docker_manager import DockerManager
from rag_service.runtime import RagRuntimeConfig, container_is_running

_LOG = logging.getLogger("rag_service.qdrant_health")

_REACTIVE_CONTAINER_ACTIONS = frozenset(
    {"start", "stop", "die", "destroy", "create", "kill", "restart", "pause", "unpause"}
)

_WARN_THROTTLE_SEC = 30.0


def _coerce_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return None


def _coerce_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def probe_qdrant_status(
    *,
    url: str,
    timeout_sec: float = 3.0,
    container_name: str | None = None,
    on_error_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Probe Qdrant HTTP reachability and optional Docker container state."""
    base = url.rstrip("/")
    status: dict[str, Any] = {"url": base, "running": False}
    if container_name:
        with contextlib.suppress(Exception):
            container_running = _coerce_bool(container_is_running(container_name))
            if container_running is not None:
                status["container_running"] = container_running
        status["container"] = container_name
    try:
        resp = requests.get(f"{base}/collections", timeout=timeout_sec)
        http_status = _coerce_int(resp.status_code)
        if http_status is not None:
            status["http_status"] = http_status
        if resp.ok:
            payload = resp.json()
            data = payload if isinstance(payload, dict) else {}
            collections = data.get("result", {}).get("collections", [])
            if isinstance(collections, list):
                status["running"] = True
                status["collections_count"] = len(collections)
            try:
                version_resp = requests.get(f"{base}/cluster", timeout=timeout_sec)
                if version_resp.ok:
                    cluster_payload = version_resp.json()
                    vdata = cluster_payload if isinstance(cluster_payload, dict) else {}
                    version = _coerce_str(
                        vdata.get("result", {}).get("status", {}).get("version")
                    )
                    if version is not None:
                        status["version"] = version
            except Exception:  # safe: cluster version probe is optional
                pass
    except Exception as exc:
        status["error"] = str(exc)
        if on_error_log is not None:
            on_error_log(str(exc))
    return status


def _container_name_from_event(event: dict[str, Any]) -> str:
    actor = event.get("Actor")
    if not isinstance(actor, dict):
        return ""
    attrs = actor.get("Attributes")
    if not isinstance(attrs, dict):
        return ""
    return str(attrs.get("name") or "").strip().lstrip("/")


class QdrantHealthMonitor:
    """Polls Qdrant on an interval and reacts to Docker container lifecycle events."""

    def __init__(
        self,
        config: RagRuntimeConfig | None = None,
        *,
        poll_interval_sec: float | None = None,
    ) -> None:
        self._cfg = config or RagRuntimeConfig.from_env()
        default_poll = float(os.getenv("QDRANT_HEALTH_POLL_INTERVAL_SEC", "10"))
        self._poll_interval_sec = max(2.0, float(poll_interval_sec or default_poll))
        self._snapshot_lock = threading.Lock()
        self._probe_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._started = False
        self._last_warn_at = 0.0
        self._threads: list[threading.Thread] = []
        self._snapshot: dict[str, Any] = {
            "url": self._cfg.qdrant_http_url.rstrip("/"),
            "running": False,
        }

    @property
    def is_started(self) -> bool:
        return self._started

    def get_snapshot(self) -> dict[str, Any]:
        with self._snapshot_lock:
            return dict(self._snapshot)

    def request_immediate_probe(self) -> None:
        """Schedule an immediate probe (e.g. after manual start/stop)."""
        self._wake.set()

    def probe_now(self) -> dict[str, Any]:
        with self._probe_lock:
            snapshot = probe_qdrant_status(
                url=self._cfg.qdrant_http_url,
                timeout_sec=3.0,
                container_name=self._cfg.qdrant_container_name,
                on_error_log=self._maybe_log_probe_error,
            )
            snapshot["monitored_at"] = time.time()
            with self._snapshot_lock:
                self._snapshot = snapshot
            return dict(snapshot)

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._started = True
            self._stop.clear()
            self.probe_now()
            poll_thread = threading.Thread(
                target=self._poll_loop,
                name="qdrant-health-poll",
                daemon=True,
            )
            docker_thread = threading.Thread(
                target=self._docker_events_loop,
                name="qdrant-health-docker",
                daemon=True,
            )
            poll_thread.start()
            docker_thread.start()
            self._threads = [poll_thread, docker_thread]

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._threads.clear()
        with self._start_lock:
            self._started = False

    def _maybe_log_probe_error(self, message: str) -> None:
        now = time.time()
        if now - self._last_warn_at < _WARN_THROTTLE_SEC:
            return
        self._last_warn_at = now
        _LOG.warning("Failed to get Qdrant status: %s", message)

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            self.probe_now()
            if self._stop.wait(0):
                break
            self._wake.wait(timeout=self._poll_interval_sec)
            self._wake.clear()

    def _docker_events_loop(self) -> None:
        container_name = self._cfg.qdrant_container_name
        docker = DockerManager()
        while not self._stop.is_set():
            try:
                for event in docker.events(event_types=["container"]):
                    if self._stop.is_set():
                        return
                    if event.get("ok") is False:
                        if self._stop.wait(5.0):
                            return
                        break
                    if str(event.get("Type") or "").strip().lower() != "container":
                        continue
                    if _container_name_from_event(event) != container_name:
                        continue
                    action = str(event.get("Action") or "").strip().lower()
                    if action in _REACTIVE_CONTAINER_ACTIONS:
                        self._wake.set()
            except Exception as exc:
                _LOG.debug("Qdrant health docker events stream ended: %s", exc)
                if self._stop.wait(5.0):
                    return


_monitor: QdrantHealthMonitor | None = None
_monitor_lock = threading.Lock()


def get_qdrant_health_monitor(config: RagRuntimeConfig | None = None) -> QdrantHealthMonitor:
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = QdrantHealthMonitor(config)
        return _monitor


def ensure_qdrant_health_monitor_started(config: RagRuntimeConfig | None = None) -> QdrantHealthMonitor:
    monitor = get_qdrant_health_monitor(config)
    monitor.start()
    return monitor


def get_qdrant_health_snapshot() -> dict[str, Any]:
    return get_qdrant_health_monitor().get_snapshot()


def reset_qdrant_health_monitor_for_tests() -> None:
    global _monitor
    with _monitor_lock:
        if _monitor is not None:
            _monitor.stop()
            _monitor = None


__all__ = [
    "QdrantHealthMonitor",
    "ensure_qdrant_health_monitor_started",
    "get_qdrant_health_monitor",
    "get_qdrant_health_snapshot",
    "probe_qdrant_status",
    "reset_qdrant_health_monitor_for_tests",
]
