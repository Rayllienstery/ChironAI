"""WebUI server lifecycle endpoint tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.fast
@pytest.mark.api
def test_server_stop_returns_stopping(monkeypatch: pytest.MonkeyPatch) -> None:
    shutdown = MagicMock()
    import api.http.webui_server_routes as server_routes

    monkeypatch.setattr(server_routes, "_shutdown_werkzeug_server", shutdown)

    from api.http.rag_routes import create_app

    app = create_app()
    response = app.test_client().post("/api/webui/server/stop")

    assert response.status_code == 200
    data = response.get_json() or {}
    assert data.get("status") == "stopping"
    shutdown.assert_called_once()


@pytest.mark.fast
@pytest.mark.api
def test_server_stop_route_registered_in_openapi() -> None:
    from api.http.rag_routes import create_app
    from core.openapi import build_openapi_spec

    app = create_app()
    spec = build_openapi_spec(app)
    paths = spec.get("paths") or {}
    assert "/api/webui/server/stop" in paths
    post = (paths["/api/webui/server/stop"] or {}).get("post") or {}
    assert post.get("summary") or post.get("operationId")
