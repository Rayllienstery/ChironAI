from __future__ import annotations

import os
import sys
from typing import Any


def _ensure_root_on_path() -> None:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)


class _FakeExtensionsService:
    def registry_entries(self) -> list[dict[str, Any]]:
        return [{"id": "ollama-provider", "title": "Ollama Provider"}]

    def installed_extensions(self) -> list[dict[str, Any]]:
        return [{"id": "ollama-provider", "enabled": True, "version": "0.1.0"}]

    def provider_rows(self, _runtime: Any) -> list[dict[str, Any]]:
        return [{"provider_id": "ollama", "extension_id": "ollama-provider", "models": []}]

    def extension_tabs(self, *, runtime: Any | None = None) -> list[dict[str, Any]]:
        return [
            {
                "id": "open-webui",
                "extension_id": "open-webui",
                "title": "Open WebUI",
                "icon": "web_asset",
                "status": {"running": True, "tone": "success", "message": "running"},
            }
        ]

    def ui_payload(self) -> dict[str, Any]:
        return {"extensions": [{"id": "ollama-provider", "title": "Ollama Provider", "ui_schema": {}}], "failed": []}

    def install(self, extension_id: str, *, version: str | None = None) -> dict[str, Any]:
        return {"id": extension_id, "version": version or "0.1.0", "restart_required": True}

    def remove(self, extension_id: str) -> dict[str, Any]:
        return {"id": extension_id, "removed": True, "restart_required": True}

    def enable(self, extension_id: str) -> dict[str, Any]:
        return {"id": extension_id, "enabled": True, "restart_required": True}

    def disable(self, extension_id: str) -> dict[str, Any]:
        return {"id": extension_id, "enabled": False, "restart_required": True}


def test_extensions_routes_expose_registry_and_ui() -> None:
    _ensure_root_on_path()
    from api.http.rag_routes import create_app

    app = create_app()
    app.extensions["llm_extensions_service"] = _FakeExtensionsService()
    app.extensions["llm_interactor_runtime"] = object()
    client = app.test_client()

    registry = client.get("/api/webui/extensions/registry")
    installed = client.get("/api/webui/extensions/installed")
    providers = client.get("/api/webui/extensions/providers")
    tabs = client.get("/api/webui/extensions/tabs")
    ui = client.get("/api/webui/extensions/ui")

    assert registry.status_code == 200
    assert installed.status_code == 200
    assert providers.status_code == 200
    assert tabs.status_code == 200
    assert ui.status_code == 200
    assert (registry.get_json() or {}).get("registry")[0]["id"] == "ollama-provider"
    assert (providers.get_json() or {}).get("providers")[0]["provider_id"] == "ollama"
    assert (tabs.get_json() or {}).get("tabs")[0]["status"]["running"] is True
    assert (ui.get_json() or {}).get("extensions")[0]["id"] == "ollama-provider"


def test_open_webui_core_routes_are_removed() -> None:
    _ensure_root_on_path()
    from api.http.rag_routes import create_app

    app = create_app()
    client = app.test_client()

    assert client.get("/api/webui/open-webui/status").status_code == 404
    assert client.get("/api/webui/open-webui/config").status_code == 404
    assert client.post("/api/webui/open-webui/start").status_code == 404
    assert client.post("/api/webui/open-webui/stop").status_code == 404


def test_extension_lifecycle_routes_return_restart_required() -> None:
    _ensure_root_on_path()
    from api.http.rag_routes import create_app

    app = create_app()
    app.extensions["llm_extensions_service"] = _FakeExtensionsService()
    client = app.test_client()

    install = client.post("/api/webui/extensions/install", json={"extension_id": "ollama-provider"})
    disable = client.post("/api/webui/extensions/disable", json={"extension_id": "ollama-provider"})
    enable = client.post("/api/webui/extensions/enable", json={"extension_id": "ollama-provider"})
    remove = client.post("/api/webui/extensions/remove", json={"extension_id": "ollama-provider"})

    assert install.status_code == 202
    assert disable.status_code == 202
    assert enable.status_code == 202
    assert remove.status_code == 202
    assert (install.get_json() or {}).get("restart_required") is True
    assert (disable.get_json() or {}).get("restart_required") is True
    assert (enable.get_json() or {}).get("restart_required") is True
    assert (remove.get_json() or {}).get("restart_required") is True
