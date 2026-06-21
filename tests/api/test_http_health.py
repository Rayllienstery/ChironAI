"""Health endpoint integration tests (split from test_http_endpoints.py)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.api.http_fixtures import set_extensions_app_state


@pytest.mark.fast
@pytest.mark.api
def test_ready_endpoint_matches_health_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = MagicMock()
    ok.ok = True
    monkeypatch.setattr("infrastructure.stack_health.requests.get", lambda *_a, **_k: ok)

    class _HealthyProviderExtensions:
        runtime = object()

        def provider_rows(self, _runtime: Any) -> list[dict[str, Any]]:
            return [
                {
                    "provider_id": "ollama",
                    "extension_id": "ollama-provider",
                    "title": "Ollama",
                    "health": {"ok": True, "status": "ok", "message": "", "details": {}},
                }
            ]

    from api.http.rag_routes import create_app

    app = create_app()
    set_extensions_app_state(app, service=_HealthyProviderExtensions(), runtime=_HealthyProviderExtensions.runtime)
    r = app.test_client().get("/ready")
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("probe") == "ready"
    assert data.get("status") == "healthy"


@pytest.mark.fast
@pytest.mark.api
def test_health_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = MagicMock()
    ok.ok = True

    def fake_get(url: str, timeout: float = 0) -> MagicMock:
        return ok

    monkeypatch.setattr("infrastructure.stack_health.requests.get", fake_get)

    class _HealthyProviderExtensions:
        runtime = object()

        def provider_rows(self, _runtime: Any) -> list[dict[str, Any]]:
            return [
                {
                    "provider_id": "ollama",
                    "extension_id": "ollama-provider",
                    "title": "Ollama",
                    "health": {"ok": True, "status": "ok", "message": "", "details": {}},
                }
            ]

    from api.http.rag_routes import create_app

    app = create_app()
    set_extensions_app_state(app, service=_HealthyProviderExtensions(), runtime=_HealthyProviderExtensions.runtime)
    client = app.test_client()
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("status") == "healthy"
    assert data.get("service") == "rag_proxy"
    comps = data.get("components") or {}
    assert comps.get("ollama") == "healthy"
    assert comps.get("qdrant") == "healthy"
    assert data.get("timestamp")
    assert r.headers.get("X-Request-Id")


@pytest.mark.fast
@pytest.mark.api
def test_metrics_endpoint_exports_prometheus_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = MagicMock()
    ok.ok = True
    monkeypatch.setattr("infrastructure.stack_health.requests.get", lambda *_a, **_k: ok)

    class _HealthyProviderExtensions:
        runtime = object()

        def provider_rows(self, _runtime: Any) -> list[dict[str, Any]]:
            return [
                {
                    "provider_id": "ollama",
                    "extension_id": "ollama-provider",
                    "title": "Ollama",
                    "health": {"ok": True, "status": "ok", "message": "", "details": {}},
                }
            ]

    from api.http.rag_routes import create_app

    app = create_app()
    set_extensions_app_state(app, service=_HealthyProviderExtensions(), runtime=_HealthyProviderExtensions.runtime)
    client = app.test_client()

    health = client.get("/health", headers={"X-Request-Id": "req-metrics-1"})
    assert health.status_code == 200
    assert health.headers.get("X-Request-Id") == "req-metrics-1"

    response = client.get("/metrics")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "text/plain" in response.content_type
    assert "chironai_http_requests_total" in text
    assert "chironai_http_request_duration_seconds" in text
    assert 'endpoint="health"' in text


@pytest.mark.fast
@pytest.mark.api
def test_health_endpoint_503_when_qdrant_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    ollama_ok = MagicMock()
    ollama_ok.ok = True
    qdrant_bad = MagicMock()
    qdrant_bad.ok = False

    def fake_get(url: str, timeout: float = 0) -> MagicMock:
        if "qdrant" in url or "/collections" in url:
            return qdrant_bad
        return ollama_ok

    monkeypatch.setattr("infrastructure.stack_health.requests.get", fake_get)

    from api.http.rag_routes import create_app

    app = create_app()
    r = app.test_client().get("/health")
    assert r.status_code == 503
    data = r.get_json() or {}
    assert data.get("status") == "unhealthy"
    assert (data.get("components") or {}).get("qdrant") == "unhealthy"


@pytest.mark.fast
@pytest.mark.api
def test_health_endpoint_uses_provider_health_when_runtime_available(monkeypatch: pytest.MonkeyPatch) -> None:
    qdrant_ok = MagicMock()
    qdrant_ok.ok = True
    requested: list[str] = []

    def fake_get(url: str, timeout: float = 0) -> MagicMock:
        requested.append(url)
        return qdrant_ok

    class FakeExtensionsService:
        runtime = object()

        def provider_rows(self, _runtime: Any) -> list[dict[str, Any]]:
            return [
                {
                    "provider_id": "ollama",
                    "extension_id": "ollama-provider",
                    "title": "Ollama",
                    "health": {"ok": True, "status": "ok", "message": "", "details": {}},
                }
            ]

    monkeypatch.setattr("infrastructure.stack_health.requests.get", fake_get)

    from api.http.rag_routes import create_app

    app = create_app()
    set_extensions_app_state(app, service=FakeExtensionsService(), runtime=FakeExtensionsService.runtime)
    r = app.test_client().get("/health")

    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("status") == "healthy"
    assert (data.get("components") or {}).get("ollama") == "healthy"
    assert (data.get("components") or {}).get("qdrant") == "healthy"
    assert requested and all("/api/tags" not in url for url in requested)


@pytest.mark.fast
@pytest.mark.api
def test_health_endpoint_503_when_provider_health_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    qdrant_ok = MagicMock()
    qdrant_ok.ok = True

    class FakeExtensionsService:
        runtime = object()

        def provider_rows(self, _runtime: Any) -> list[dict[str, Any]]:
            return [
                {
                    "provider_id": "ollama",
                    "extension_id": "ollama-provider",
                    "title": "Ollama",
                    "health": {"ok": False, "status": "error", "message": "offline", "details": {}},
                }
            ]

    monkeypatch.setattr("infrastructure.stack_health.requests.get", lambda *_a, **_k: qdrant_ok)

    from api.http.rag_routes import create_app

    app = create_app()
    set_extensions_app_state(app, service=FakeExtensionsService(), runtime=FakeExtensionsService.runtime)
    r = app.test_client().get("/health")

    assert r.status_code == 503
    data = r.get_json() or {}
    assert data.get("status") == "unhealthy"
    assert (data.get("components") or {}).get("ollama") == "unhealthy"
    assert (data.get("components") or {}).get("qdrant") == "healthy"
