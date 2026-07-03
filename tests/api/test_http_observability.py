"""Observability routes: logs, proxy logs/traces, notifications (split from test_http_endpoints.py)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.api.http_fixtures import webui_blueprint_client as _webui_blueprint_client


def test_proxy_logs_passes_autocomplete_only_to_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/webui/proxy-logs?autocomplete_only=1 filters autocomplete rows in the repository."""
    import api.http.webui_observability_routes as wr

    last_kwargs: dict = {}

    class FakeRepo:
        def get_logs(self, **kwargs):
            last_kwargs.clear()
            last_kwargs.update(kwargs)
            return []

        def add_log(self, *args: Any, **kwargs: Any) -> int:
            return 1

    monkeypatch.setattr(wr, "get_logs_repository", lambda: FakeRepo())

    from api.http.rag_routes import create_app

    client = create_app().test_client()
    r = client.get("/api/webui/proxy-logs?autocomplete_only=1&limit=5")
    assert r.status_code == 200
    assert last_kwargs.get("autocomplete_only") is True
    assert last_kwargs.get("session_id") == "proxy"


def test_proxy_logs_default_no_autocomplete_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.webui_observability_routes as wr

    last_kwargs: dict = {}

    class FakeRepo:
        def get_logs(self, **kwargs):
            last_kwargs.clear()
            last_kwargs.update(kwargs)
            return []

        def add_log(self, *args: Any, **kwargs: Any) -> int:
            return 1

    monkeypatch.setattr(wr, "get_logs_repository", lambda: FakeRepo())

    from api.http.rag_routes import create_app

    client = create_app().test_client()
    r = client.get("/api/webui/proxy-logs?limit=5")
    assert r.status_code == 200
    assert last_kwargs.get("autocomplete_only") is None


def test_webui_logs_passes_since_id_zero_to_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    """since_id=0 must reach the repository (incremental poll), not be treated as absent."""
    import api.http.webui_observability_routes as wr

    last_kwargs: dict = {}

    class FakeRepo:
        def get_logs(self, **kwargs):
            last_kwargs.clear()
            last_kwargs.update(kwargs)
            return []

        def add_log(self, *args: Any, **kwargs: Any) -> int:
            return 1

    monkeypatch.setattr(wr, "get_logs_repository", lambda: FakeRepo())

    client = _webui_blueprint_client()
    r = client.get("/api/webui/logs?session_id=test-session&since_id=0&limit=10")
    assert r.status_code == 200
    assert last_kwargs.get("since_id") == 0


def test_webui_logs_omitted_since_id_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """When since_id is omitted, repository should see since_id=None."""
    import api.http.webui_observability_routes as wr

    last_kwargs: dict = {}

    class FakeRepo:
        def get_logs(self, **kwargs):
            last_kwargs.clear()
            last_kwargs.update(kwargs)
            return []

        def add_log(self, *args: Any, **kwargs: Any) -> int:
            return 1

    monkeypatch.setattr(wr, "get_logs_repository", lambda: FakeRepo())

    client = _webui_blueprint_client()
    r = client.get("/api/webui/logs?session_id=test-session&limit=10")
    assert r.status_code == 200
    assert last_kwargs.get("since_id") is None


def test_webui_logs_create_and_delete_routes_use_observability_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.webui_observability_routes as wr

    calls: dict[str, Any] = {}

    class FakeRepo:
        def add_log(self, **kwargs):
            calls["add"] = kwargs
            return 42

        def delete_logs_for_session(self, session_id: str, *, include_system: bool) -> int:
            calls["delete"] = {"session_id": session_id, "include_system": include_system}
            return 3

    monkeypatch.setattr(wr, "get_logs_repository", lambda: FakeRepo())

    client = _webui_blueprint_client()
    created = client.post(
        "/api/webui/logs",
        json={"session_id": "s1", "level": "warning", "message": "hello", "source": "test"},
    )
    deleted = client.delete("/api/webui/logs?session_id=s1&include_system=0")

    assert created.status_code == 200
    assert created.get_json()["id"] == 42
    assert calls["add"]["level"] == "WARNING"
    assert deleted.status_code == 200
    assert deleted.get_json()["deleted_count"] == 3
    assert calls["delete"] == {"session_id": "s1", "include_system": False}


def test_proxy_logs_delete_and_trace_current_routes_remain_available(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.webui_observability_routes as wr

    calls: dict[str, Any] = {}

    class FakeRepo:
        def delete_proxy_logs(self, *, autocomplete_only: bool) -> int:
            calls["delete_proxy_logs"] = autocomplete_only
            return 5

    monkeypatch.setattr(wr, "get_logs_repository", lambda: FakeRepo())
    monkeypatch.setattr(wr, "get_current_trace", lambda: {"request_id": "r1"})
    monkeypatch.setattr(wr, "get_active_traces", lambda: [{"request_id": "r1"}])
    monkeypatch.setattr(wr, "get_current_trace_updated_at", lambda: "2026-05-15T00:00:00Z")
    monkeypatch.setattr(wr, "get_proxy_status_label", lambda: "running")

    client = _webui_blueprint_client()
    deleted = client.delete("/api/webui/proxy-logs?autocomplete_only=1")
    trace = client.get("/api/webui/proxy-trace/current")

    assert deleted.status_code == 200
    assert deleted.get_json()["deleted_count"] == 5
    assert calls["delete_proxy_logs"] is True
    assert trace.status_code == 200
    assert trace.get_json() == {
        "active_traces": [{"request_id": "r1"}],
        "status": "running",
        "trace": {"request_id": "r1"},
        "updated_at": "2026-05-15T00:00:00Z",
    }


def test_notifications_routes_use_observability_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.webui_observability_routes as wr

    calls: dict[str, Any] = {}

    class FakeRepo:
        def list_notifications(self, *, session_id: str, limit: int, include_dismissed: bool):
            calls.setdefault("list", []).append((session_id, limit, include_dismissed))
            return [{"id": 7, "created_at": "2026-05-15T00:00:00Z"}] if session_id == "s1" else []

        def add_notification(self, **kwargs):
            calls["add"] = kwargs
            return 7

        def dismiss(self, session_id: str, nid: int) -> bool:
            calls["dismiss"] = (session_id, nid)
            return True

        def clear_session(self, session_id: str) -> int:
            calls["clear"] = session_id
            return 1

    monkeypatch.setattr(wr, "get_notifications_repository", lambda: FakeRepo())

    client = _webui_blueprint_client()
    listed = client.get("/api/webui/notifications?session_id=s1&include_dismissed=0")
    created = client.post(
        "/api/webui/notifications",
        json={"session_id": "s1", "kind": "info", "source": "test", "title": "Title", "message": "Body"},
    )
    dismissed = client.patch("/api/webui/notifications/7/dismiss", json={"session_id": "s1"})
    cleared = client.post("/api/webui/notifications/clear", json={"session_id": "s1"})

    assert listed.status_code == 200
    assert listed.get_json()["notifications"][0]["id"] == 7
    assert calls["list"][0] == ("s1", 200, False)
    assert created.status_code == 200
    assert created.get_json()["id"] == 7
    assert dismissed.status_code == 200
    assert calls["dismiss"] == ("s1", 7)
    assert cleared.status_code == 200
    assert cleared.get_json()["deleted"] == 1


def test_proxy_journal_passes_offset_and_returns_total(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.webui_observability_routes as wr

    last_kwargs: dict = {}
    count_kwargs: dict = {}

    class FakeRepo:
        def get_proxy_journal_groups(self, **kwargs):
            last_kwargs.clear()
            last_kwargs.update(kwargs)
            return [{"id": 3}, {"id": 2}]

        def count_proxy_journal_groups(self, **kwargs):
            count_kwargs.clear()
            count_kwargs.update(kwargs)
            return 42

        def get_logs(self, **kwargs):
            return []

        def add_log(self, *args: Any, **kwargs: Any) -> int:
            return 1

    monkeypatch.setattr(wr, "get_logs_repository", lambda: FakeRepo())

    client = _webui_blueprint_client()
    r = client.get("/api/webui/proxy-journal?limit=50&offset=50")

    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["total"] == 42
    assert body["offset"] == 50
    assert body["limit"] == 50
    assert last_kwargs.get("offset") == 50


def test_proxy_journal_since_id_skips_total_and_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.webui_observability_routes as wr

    last_kwargs: dict = {}
    count_called = False

    class FakeRepo:
        def get_logs(self, **kwargs):
            last_kwargs.clear()
            last_kwargs.update(kwargs)
            return [{"id": 8}]

        def count_logs(self, **kwargs):
            nonlocal count_called
            count_called = True
            return 0

        def add_log(self, *args: Any, **kwargs: Any) -> int:
            return 1

    monkeypatch.setattr(wr, "get_logs_repository", lambda: FakeRepo())

    client = _webui_blueprint_client()
    r = client.get("/api/webui/proxy-journal?since_id=7&limit=25")

    assert r.status_code == 200
    body = r.get_json()
    assert body == {"ok": True, "logs": [{"id": 8}]}
    assert last_kwargs.get("since_id") == 7
    assert last_kwargs.get("newest_first") is True
    assert "offset" not in last_kwargs or last_kwargs.get("offset", 0) == 0
    assert count_called is False

