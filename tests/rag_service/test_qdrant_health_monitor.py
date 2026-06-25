"""Tests for background Qdrant health monitor."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from rag_service.qdrant_health_monitor import (
    QdrantHealthMonitor,
    probe_qdrant_status,
    reset_qdrant_health_monitor_for_tests,
)
from rag_service.runtime import RagRuntimeConfig


def teardown_function() -> None:
    reset_qdrant_health_monitor_for_tests()


def test_probe_qdrant_status_success() -> None:
    fake_resp = MagicMock()
    fake_resp.ok = True
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"result": {"collections": [{"name": "a"}, {"name": "b"}]}}

    fake_cluster = MagicMock()
    fake_cluster.ok = True
    fake_cluster.json.return_value = {"result": {"status": {"version": "1.12.5"}}}

    def _fake_get(url: str, **kwargs: object) -> MagicMock:
        if url.endswith("/cluster"):
            return fake_cluster
        return fake_resp

    with (
        patch("rag_service.qdrant_health_monitor.container_is_running", return_value=True),
        patch("rag_service.qdrant_health_monitor.requests.get", side_effect=_fake_get),
    ):
        snap = probe_qdrant_status(url="http://localhost:6333", container_name="qdrant")

    assert snap["running"] is True
    assert snap["collections_count"] == 2
    assert snap["version"] == "1.12.5"
    assert snap["container_running"] is True


def test_probe_qdrant_status_failure() -> None:
    with patch(
        "rag_service.qdrant_health_monitor.requests.get",
        side_effect=ConnectionError("Connection aborted."),
    ):
        snap = probe_qdrant_status(url="http://localhost:6333")

    assert snap["running"] is False
    assert "Connection aborted" in str(snap.get("error") or "")


def test_monitor_stores_snapshot_and_serves_cache() -> None:
    cfg = RagRuntimeConfig.from_env()
    monitor = QdrantHealthMonitor(cfg, poll_interval_sec=60.0)

    fake_resp = MagicMock()
    fake_resp.ok = False
    fake_resp.status_code = 503

    with patch("rag_service.qdrant_health_monitor.requests.get", return_value=fake_resp):
        snap = monitor.probe_now()

    assert snap["running"] is False
    assert monitor.get_snapshot()["http_status"] == 503


def test_monitor_reacts_to_docker_container_start_event() -> None:
    cfg = RagRuntimeConfig.from_env()
    monitor = QdrantHealthMonitor(cfg, poll_interval_sec=60.0)

    events = [
        {"ok": True, "Type": "container", "Action": "start", "Actor": {"Attributes": {"name": cfg.qdrant_container_name}}},
    ]

    class _FakeDocker:
        def events(self, *, event_types: list[str] | None = None):
            yield from events

    probe_calls = {"count": 0}
    original_probe = monitor.probe_now

    def _counting_probe() -> dict[str, object]:
        probe_calls["count"] += 1
        return original_probe()

    with (
        patch("rag_service.qdrant_health_monitor.DockerManager", return_value=_FakeDocker()),
        patch("rag_service.qdrant_health_monitor.requests.get", side_effect=ConnectionError("down")),
        patch.object(monitor, "probe_now", side_effect=_counting_probe),
    ):
        monitor.start()
        deadline = time.monotonic() + 2.0
        while probe_calls["count"] < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        monitor.stop()

    assert probe_calls["count"] >= 2


def test_monitor_poll_loop_runs_periodically() -> None:
    cfg = RagRuntimeConfig.from_env()
    monitor = QdrantHealthMonitor(cfg, poll_interval_sec=0.2)

    probe_calls = {"count": 0}
    original_probe = monitor.probe_now

    def _counting_probe() -> dict[str, object]:
        probe_calls["count"] += 1
        return original_probe()

    with (
        patch("rag_service.qdrant_health_monitor.DockerManager") as docker_cls,
        patch("rag_service.qdrant_health_monitor.requests.get", side_effect=ConnectionError("down")),
        patch.object(monitor, "probe_now", side_effect=_counting_probe),
    ):
        docker_cls.return_value.events.return_value = iter(())
        monitor.start()
        time.sleep(0.55)
        monitor.stop()

    assert probe_calls["count"] >= 2
