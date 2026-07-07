"""Tests for the production WebUI app factory."""

from __future__ import annotations

import pytest


@pytest.mark.fast
@pytest.mark.webui
def test_create_production_app_registers_webui_routes() -> None:
    from webui_backend.app_factory import create_production_app

    app = create_production_app(bootstrap_extensions=False, warm_session=False)
    client = app.test_client()

    webui = client.get("/webui")
    assert webui.status_code in (200, 404)

    root = client.get("/")
    assert root.status_code in (302, 200)

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/webui" in rules
    assert "/api/webui/sessions" in rules or any(r.startswith("/api/webui") for r in rules)
