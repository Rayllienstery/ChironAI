from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest


def _ensure_root_on_path() -> None:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)


@pytest.fixture(autouse=True)
def _disable_background_extension_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_root_on_path()
    from llm_interactor import ExtensionManager

    monkeypatch.setattr(ExtensionManager, "start_background_bootstrap", lambda self: None)


class _FakeExtensionsService:
    def registry_entries(self) -> list[dict[str, Any]]:
        return [{"id": "ollama-provider", "title": "Ollama"}]

    def installed_extensions(self) -> list[dict[str, Any]]:
        return [{"id": "ollama-provider", "enabled": True, "version": "0.1.0"}]

    def provider_rows(self, _runtime: Any) -> list[dict[str, Any]]:
        return [
            {
                "provider_id": "ollama",
                "extension_id": "ollama-provider",
                "title": "Ollama",
                "capabilities": {"chat": True},
                "models": [{"id": "tiny-model:latest", "label": "tiny-model:latest", "description": "test model"}],
            }
        ]

    def provider_catalog(self, *, runtime: Any | None = None, capability: str | None = None) -> dict[str, Any]:
        rows = self.provider_rows(runtime)
        return {
            "providers": rows,
            "models": [
                {
                    "provider_id": "ollama",
                    "provider_title": "Ollama",
                    "extension_id": "ollama-provider",
                    "id": "tiny-model:latest",
                    "name": "tiny-model:latest",
                    "label": "tiny-model:latest",
                    "description": "test model",
                    "metadata": {},
                }
            ],
        }

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
        return {"extensions": [{"id": "ollama-provider", "title": "Ollama", "ui_schema": {}}], "failed": []}

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
    catalog = client.get("/api/webui/providers/catalog")
    models = client.get("/api/webui/models")
    tabs = client.get("/api/webui/extensions/tabs")
    ui = client.get("/api/webui/extensions/ui")

    assert registry.status_code == 200
    assert installed.status_code == 200
    assert providers.status_code == 200
    assert catalog.status_code == 200
    assert models.status_code == 200
    assert tabs.status_code == 200
    assert ui.status_code == 200
    assert (registry.get_json() or {}).get("registry")[0]["id"] == "ollama-provider"
    assert (registry.get_json() or {}).get("registry")[0]["title"] == "Ollama"
    provider = (providers.get_json() or {}).get("providers")[0]
    assert provider["provider_id"] == "ollama"
    assert provider["title"] == "Ollama"
    assert (catalog.get_json() or {}).get("models")[0]["provider_title"] == "Ollama"
    assert any(model.get("provider_title") == "Ollama" for model in (models.get_json() or {}).get("models") or [])
    assert (tabs.get_json() or {}).get("tabs")[0]["status"]["running"] is True
    assert (ui.get_json() or {}).get("extensions")[0]["id"] == "ollama-provider"
    assert (ui.get_json() or {}).get("extensions")[0]["title"] == "Ollama"


def test_create_app_syncs_extension_runtime_after_background_bootstrap() -> None:
    _ensure_root_on_path()
    from api.http.rag_routes import create_app

    app = create_app()
    manager = app.extensions["llm_extensions_service"]
    runtime = object()
    registry = object()
    manager._runtime = runtime
    manager._registry = registry

    assert "llm_interactor_runtime" not in app.extensions
    assert "llm_provider_registry" not in app.extensions

    response = app.test_client().get("/")

    assert response.status_code == 302
    assert app.extensions["llm_interactor_runtime"] is runtime
    assert app.extensions["llm_provider_registry"] is registry


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


def test_extension_asset_route_serves_installed_assets_and_blocks_escape(tmp_path: Path) -> None:
    _ensure_root_on_path()
    from api.http.rag_routes import create_app
    from llm_interactor import ExtensionManager, ExtensionRegistryClient, ProviderHostContext

    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=root / "extensions" / "bundled",
    )
    manager.ensure_bundled_installed()

    app = create_app()
    app.extensions["llm_extensions_service"] = manager
    client = app.test_client()

    ok = client.get("/api/webui/extensions/open-webui/assets/icons/open-webui-light.svg")
    escaped = client.get("/api/webui/extensions/open-webui/assets/../chironai-extension.json")
    missing = client.get("/api/webui/extensions/open-webui/assets/icons/missing.svg")

    assert ok.status_code == 200
    assert b"<svg" in ok.data
    assert escaped.status_code == 404
    assert missing.status_code == 404
