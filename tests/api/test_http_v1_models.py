"""V1 models and Ollama compatibility route tests (split from test_http_endpoints.py)."""

from __future__ import annotations

import pytest

from tests.api.http_fixtures import (
    test_proxy_api_key_setting as _test_proxy_api_key_setting,
)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/tags"),
        ("post", "/api/show"),
        ("post", "/api/generate"),
        ("post", "/api/chat"),
        ("post", "/v1/completions"),
    ],
)
def test_ollama_compatibility_routes_are_removed(method: str, path: str) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

    from api.http.rag_routes import create_app

    client = create_app().test_client()
    request_fn = getattr(client, method)
    r = request_fn(path, json={"model": "tiny-model"})
    assert r.status_code == 404


def test_models_endpoint() -> None:
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from api.http.rag_routes import create_app
    app = create_app()
    client = app.test_client()
    r = client.get("/v1/models")
    assert r.status_code == 200
    data = r.get_json()
    assert "data" in data
    assert isinstance(data["data"], list)
    for m in data["data"]:
        assert m.get("supports_vision") is True
        assert m.get("supportsImages") is True
        assert m.get("supports_images") is True
        assert m.get("attachment") is True
        assert m.get("input_modalities") == ["text", "image"]
        assert m.get("modalities") == {"input": ["text", "image"], "output": ["text"]}
        assert "vision" in (m.get("capabilities") or [])


def test_models_endpoint_includes_chironai_autocomplete_when_backend_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second logical id appears in /v1/models when autocomplete Ollama tag is set (env or WebUI)."""
    import os
    import sys

    monkeypatch.setenv("LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL", "tiny-model:latest")
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from api.http.rag_routes import create_app

    client = create_app().test_client()
    r = client.get("/v1/models")
    assert r.status_code == 200
    data = r.get_json() or {}
    ids = [m.get("id") for m in data.get("data") or []]
    assert "ChironAI-Autocomplete" in ids
    ac = next(m for m in (data.get("data") or []) if m.get("id") == "ChironAI-Autocomplete")
    assert ac.get("supports_vision") is True
    assert ac.get("supportsImages") is True
    assert ac.get("attachment") is True
    assert ac.get("input_modalities") == ["text", "image"]
    assert ac.get("modalities") == {"input": ["text", "image"], "output": ["text"]}


def test_v1_retrieve_model_exposes_vision_aliases_for_build_and_upstream_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Agent-high",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "kimi-k2.7-code:cloud",
                            "prompt_name": "system_senior_ios_assistant_v1",
                        }
                    ]
                )
            return _test_proxy_api_key_setting(key)

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())

    client = rag_routes.create_app().test_client()

    build_response = client.get("/v1/models/Agent-high")
    assert build_response.status_code == 200
    build_row = build_response.get_json() or {}
    assert build_row.get("id") == "Agent-high"
    assert build_row.get("supportsImages") is True
    assert build_row.get("input_modalities") == ["text", "image"]
    assert "vision" in (build_row.get("capabilities") or [])

    upstream_response = client.get("/v1/models/kimi-k2.7-code:cloud")
    assert upstream_response.status_code == 200
    upstream_row = upstream_response.get_json() or {}
    assert upstream_row.get("id") == "kimi-k2.7-code:cloud"
    assert upstream_row.get("supportsImages") is True
    assert upstream_row.get("modalities") == {"input": ["text", "image"], "output": ["text"]}
    assert (upstream_row.get("metadata") or {}).get("synthetic") is True


def test_models_endpoint_exposes_build_context_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Agent-high",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "deepseek-v4-pro:cloud",
                            "prompt_name": "system_senior_ios_assistant_v1",
                            "num_ctx": 131072,
                        }
                    ]
                )
            return _test_proxy_api_key_setting(key)

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())

    app = rag_routes.create_app()
    r = app.test_client().get("/v1/models")

    assert r.status_code == 200
    data = r.get_json() or {}
    row = next(m for m in data.get("data") or [] if m.get("id") == "Agent-high")
    assert row.get("context_length") == 131072
    assert row.get("attachment") is True
    assert row.get("modalities") == {"input": ["text", "image"], "output": ["text"]}
    assert row.get("num_ctx") == 131072
    assert (row.get("metadata") or {}).get("context_length") == 131072
    assert (row.get("metadata") or {}).get("num_ctx") == 131072

