from __future__ import annotations

from typing import Any

import pytest

PRODUCT_HARDENING_FLOWS = {
    "app_start": "GET /api/webui/performance/startup",
    "coreui_dashboard": "GET /",
    "rag_status": "GET /api/webui/rag/status",
    "llm_proxy_chat": "tests/api/test_http_endpoints.py covers /v1/chat/completions",
    "extension_lifecycle": "tests/api/test_extensions_routes.py covers install/enable/disable/remove",
    "ollama_provider_actions": "tests/api/test_extensions_routes.py covers generic Ollama provider actions",
    "docker_actions": "GET /api/webui/docker/status plus destructive confirmation tests",
    "logs_proxy_traces": "GET /api/webui/logs and /api/webui/proxy-trace/current",
}


@pytest.fixture(autouse=True)
def _disable_background_extension_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    from llm_interactor import ExtensionManager

    monkeypatch.setattr(ExtensionManager, "start_background_bootstrap", lambda self: None)


class _FakeDockerManager:
    def status(self) -> dict[str, Any]:
        return {"ok": True, "cli_available": True, "engine_ready": True}

    def containers(self) -> dict[str, Any]:
        return {"ok": True, "containers": [{"name": "qdrant", "running": True}]}

    def images(self) -> dict[str, Any]:
        return {"ok": True, "images": [{"image": "qdrant/qdrant:latest"}]}


class _FakeExtensionsService:
    def installed_extensions(self, *, include_docker_versions: bool = True) -> list[dict[str, Any]]:
        return [
            {
                "id": "ollama-provider",
                "enabled": True,
                "version": "0.1.0",
                "security_blocked": False,
                "security_findings": [],
                "sandboxed": True,
                "sandbox_status": "ready",
                "sandbox_blocked": False,
            }
        ]

    def registry_entries(self) -> list[dict[str, Any]]:
        return [{"id": "ollama-provider", "title": "Ollama"}]

    def registry_diagnostics(self) -> dict[str, Any]:
        return {"registry_url": "https://example.invalid/extensions.json", "diagnostics": [], "entries_count": 1}


def _create_hardened_app(monkeypatch: pytest.MonkeyPatch) -> Any:
    import api.http.webui_docker_routes as docker_routes
    from api.http.extensions_service_access import set_extensions_runtime, set_extensions_service
    from api.http.rag_routes import create_app

    monkeypatch.setattr(docker_routes, "DockerManager", _FakeDockerManager)
    app = create_app()
    set_extensions_service(app, _FakeExtensionsService())
    set_extensions_runtime(app, object())
    return app


def test_product_hardening_flow_matrix_covers_phase_8() -> None:
    assert set(PRODUCT_HARDENING_FLOWS) == {
        "app_start",
        "coreui_dashboard",
        "rag_status",
        "llm_proxy_chat",
        "extension_lifecycle",
        "ollama_provider_actions",
        "docker_actions",
        "logs_proxy_traces",
    }
    assert all(PRODUCT_HARDENING_FLOWS.values())


def test_product_readonly_flows_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _create_hardened_app(monkeypatch)
    client = app.test_client()

    checks = {
        "coreui_dashboard": client.get("/"),
        "app_start": client.get("/api/webui/performance/startup"),
        "version": client.get("/api/webui/version"),
        "rag_status": client.get("/api/webui/rag/status"),
        "docker_status": client.get("/api/webui/docker/status"),
        "extensions_installed": client.get("/api/webui/extensions/installed?docker_versions=0"),
        "logs": client.get("/api/webui/logs?session_id=product-smoke&limit=1"),
        "proxy_trace_current": client.get("/api/webui/proxy-trace/current"),
        "proxy_traces": client.get("/api/webui/proxy-traces?limit=1"),
    }

    assert checks["coreui_dashboard"].status_code in {200, 302}
    for name, response in checks.items():
        if name == "coreui_dashboard":
            continue
        assert response.status_code == 200, name

    version = checks["version"].get_json() or {}
    assert {"version", "app_name", "stage", "display_name"} <= set(version)
    docker = checks["docker_status"].get_json() or {}
    assert docker["engine_ready"] is True
    installed = checks["extensions_installed"].get_json() or {}
    assert installed["extensions"][0]["id"] == "ollama-provider"


def test_product_security_headers_are_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _create_hardened_app(monkeypatch)
    response = app.test_client().get("/api/webui/version")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "Strict-Transport-Security" not in response.headers
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp


def test_product_destructive_docker_actions_require_exact_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _create_hardened_app(monkeypatch)
    client = app.test_client()

    missing = client.delete("/api/webui/docker/images", json={"image": "qdrant/qdrant:latest"})
    wrong = client.delete(
        "/api/webui/docker/images",
        json={"image": "qdrant/qdrant:latest", "confirm": "qdrant"},
    )

    assert missing.status_code == 400
    assert wrong.status_code == 400
    assert (missing.get_json() or {})["code"] == "confirmation_required"
    assert (wrong.get_json() or {})["code"] == "confirmation_required"
