"""Security headers on the real WebUI Flask entrypoint."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_background_extension_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    from llm_interactor import ExtensionManager

    monkeypatch.setattr(ExtensionManager, "start_background_bootstrap", lambda self: None)


def test_webui_backend_app_applies_security_headers() -> None:
    from webui_backend.app import app

    response = app.test_client().get("/api/webui/version")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "Strict-Transport-Security" not in response.headers
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    assert "'unsafe-inline'" in csp
    assert "'unsafe-eval'" in csp


def test_hsts_is_sent_only_on_https() -> None:
    from webui_backend.app import app

    https_response = app.test_client().get("/api/webui/version", base_url="https://localhost")

    assert https_response.status_code == 200
    assert https_response.headers["Strict-Transport-Security"].startswith("max-age=31536000")
