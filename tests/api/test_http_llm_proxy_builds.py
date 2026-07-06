"""LLM Proxy builds routes (split from test_http_endpoints.py)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.api.http_fixtures import set_extensions_app_state as _set_extensions_app_state


def test_llm_proxy_builds_diagnostics_zero_returns_light_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/webui/llm-proxy/builds?diagnostics=0 skips heavy Ollama/Qdrant enrichment."""
    import api.http.webui_routes as wr

    sample = [
        {
            "id": "devbuild",
            "backend": "dumb",
            "provider_id": "ollama",
            "model": "llama3.2:latest",
            "prompt_name": "system_senior_ios_assistant_v1",
            "use_prompt_template": True,
            "ide_mode": True,
        }
    ]

    class FakeSettings:
        def get_app_setting(self, key: str) -> str | None:
            if key == wr.LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(sample)
            return None

    called: list[str] = []

    def boom_enrich(_builds: list) -> list:
        called.append("enrich")
        raise AssertionError("enrich should not run when diagnostics=0")

    monkeypatch.setattr(wr, "get_settings_repository", lambda: FakeSettings())
    monkeypatch.setattr(wr, "_enrich_builds_with_diagnostics", boom_enrich)

    from api.http.rag_routes import create_app

    app = create_app()
    client = app.test_client()
    r = client.get("/api/webui/llm-proxy/builds?diagnostics=0")
    assert r.status_code == 200
    assert called == []
    data = r.get_json()
    assert len(data.get("builds") or []) == 1
    row = data["builds"][0]
    assert row.get("issues") == []
    assert row.get("healthy") is True
    assert row.get("ide_mode") is True


def test_llm_proxy_builds_diagnostics_use_provider_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.webui_llm_proxy_routes as llm_proxy_routes
    import api.http.webui_routes as wr

    sample = [
        {
            "id": "present",
            "backend": "dumb",
            "provider_id": "ollama",
            "model": "tiny-model:latest",
            "use_prompt_template": False,
        },
        {
            "id": "missing",
            "backend": "dumb",
            "provider_id": "ollama",
            "model": "missing-model:latest",
            "use_prompt_template": False,
        },
    ]

    class FakeSettings:
        def get_app_setting(self, key: str) -> str | None:
            if key == wr.LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(sample)
            return None

    class FakeExtensionsService:
        runtime = object()

        def provider_catalog(self, *, runtime: Any | None = None, capability: str | None = None) -> dict[str, Any]:
            return {
                "providers": [{"provider_id": "ollama", "title": "Ollama"}],
                "models": [
                    {
                        "provider_id": "ollama",
                        "provider_title": "Ollama",
                        "id": "tiny-model:latest",
                        "label": "tiny-model:latest",
                    }
                ],
            }

    monkeypatch.setattr(wr, "get_settings_repository", lambda: FakeSettings())
    monkeypatch.setattr(llm_proxy_routes, "_get_cached_qdrant_collection_name_set_for_builds_diag", lambda: set())
    monkeypatch.setattr("api.http.webui_llm_proxy_routes.invoke_tags", lambda **_: pytest.fail("direct tags used"), raising=False)

    from api.http.rag_routes import create_app

    app = create_app()
    _set_extensions_app_state(app, service=FakeExtensionsService(), runtime=FakeExtensionsService.runtime)
    r = app.test_client().get("/api/webui/llm-proxy/builds")

    assert r.status_code == 200
    rows = {row["id"]: row for row in (r.get_json() or {}).get("builds") or []}
    assert rows["present"]["healthy"] is True
    assert rows["present"]["issues"] == []
    assert rows["missing"]["healthy"] is False
    assert any("missing-model:latest" in issue for issue in rows["missing"]["issues"])


def test_llm_proxy_build_preview_model_uses_extension_action(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeExtensionsService:
        runtime = object()

        def provider_rows(self, _runtime: Any) -> list[dict[str, Any]]:
            return [{"provider_id": "ollama", "extension_id": "ollama-provider", "title": "Ollama"}]

        def run_extension_action(
            self,
            extension_id: str,
            action_id: str,
            *,
            payload: dict[str, Any],
            runtime: Any | None = None,
        ) -> dict[str, Any]:
            calls.append(
                {
                    "extension_id": extension_id,
                    "action_id": action_id,
                    "payload": payload,
                    "runtime": runtime,
                }
            )
            return {
                "ok": True,
                "details": {
                    "model_info": {"llama.context_length": 8192},
                    "capabilities": ["completion", "thinking"],
                },
            }

    from api.http.rag_routes import create_app

    app = create_app()
    _set_extensions_app_state(app, service=FakeExtensionsService(), runtime=FakeExtensionsService.runtime)
    r = app.test_client().post("/api/webui/llm-proxy/builds/preview-model", json={"model": "tiny-model:latest"})

    assert r.status_code == 200
    assert r.get_json() == {
        "ok": True,
        "context_length": 8192,
        "supports_thinking": True,
        "capabilities": ["completion", "thinking"],
    }
    assert calls == [
        {
            "extension_id": "ollama-provider",
            "action_id": "show_model",
            "payload": {"selected_model": "tiny-model:latest"},
            "runtime": FakeExtensionsService.runtime,
        }
    ]


def test_llm_proxy_build_preview_model_reports_runtime_unavailable() -> None:
    from api.http.rag_routes import create_app

    app = create_app()
    _set_extensions_app_state(app, service=None)
    r = app.test_client().post("/api/webui/llm-proxy/builds/preview-model", json={"model": "tiny-model:latest"})

    assert r.status_code == 502
    data = r.get_json() or {}
    assert data.get("ok") is False
    assert "provider extension" in (data.get("error") or "")


def test_llm_proxy_builds_put_roundtrips_ide_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.webui_routes as wr

    class FakeSettings:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str) -> str | None:
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    fake_settings = FakeSettings()

    def light_enrich(builds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**item, "issues": [], "healthy": True} for item in builds]

    monkeypatch.setattr(wr, "get_settings_repository", lambda: fake_settings)
    monkeypatch.setattr(wr, "_enrich_builds_with_diagnostics", light_enrich)

    from api.http.rag_routes import create_app

    app = create_app()
    client = app.test_client()
    body = {
        "builds": [
            {
                "id": "Agent-high",
                "backend": "dumb",
                "provider_id": "ollama",
                "model": "qwen3:latest",
                "prompt_name": "system_senior_ios_assistant_v1",
                "ide_mode": True,
            }
        ]
    }

    r = client.put("/api/webui/llm-proxy/builds", json=body)

    assert r.status_code == 200
    data = r.get_json()
    assert data["builds"][0]["ide_mode"] is True
    stored = json.loads(fake_settings.get_app_setting(wr.LLM_PROXY_BUILDS_APP_KEY) or "[]")
    assert stored[0]["ide_mode"] is True


def test_llm_proxy_builds_put_roundtrips_rag_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.webui_routes as wr

    class FakeSettings:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str) -> str | None:
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    fake_settings = FakeSettings()

    def light_enrich(builds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**item, "issues": [], "healthy": True} for item in builds]

    monkeypatch.setattr(wr, "get_settings_repository", lambda: fake_settings)
    monkeypatch.setattr(wr, "_enrich_builds_with_diagnostics", light_enrich)

    from api.http.rag_routes import create_app

    app = create_app()
    client = app.test_client()
    body = {
        "builds": [
            {
                "id": "rag-worker",
                "backend": "dumb",
                "provider_id": "ollama",
                "model": "llama3",
                "prompt_name": "system_senior_ios_assistant_v1",
                "rag_enabled": True,
                "rag_collection": "ios-docs",
            }
        ]
    }

    put = client.put("/api/webui/llm-proxy/builds", json=body)
    assert put.status_code == 200
    assert put.get_json()["builds"][0]["rag_collection"] == "ios-docs"

    stored = json.loads(fake_settings.get_app_setting(wr.LLM_PROXY_BUILDS_APP_KEY) or "[]")
    assert stored[0]["rag_collection"] == "ios-docs"

    edit = {
        "builds": [
            {
                **body["builds"][0],
                "rag_collection": "api-docs",
            }
        ]
    }
    put_edit = client.put("/api/webui/llm-proxy/builds", json=edit)
    assert put_edit.status_code == 200
    assert put_edit.get_json()["builds"][0]["rag_collection"] == "api-docs"
    stored_after = json.loads(fake_settings.get_app_setting(wr.LLM_PROXY_BUILDS_APP_KEY) or "[]")
    assert stored_after[0]["rag_collection"] == "api-docs"
