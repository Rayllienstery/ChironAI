"""Proxy API key and /v1 auth middleware tests (split from test_http_endpoints.py)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tests.api.http_fixtures import (
    NO_TEST_PROXY_AUTH_HEADER,
    TEST_PROXY_API_KEY,
)


@pytest.mark.fast
@pytest.mark.api
def test_v1_models_returns_503_when_proxy_api_key_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.rag_routes as rag_routes
    from api.http.rag_routes import create_app

    class NoKeyRepo:
        def get_app_setting(self, key: str):
            if key == "proxy_model":
                return "fake-proxy-ollama-model"
            if key == "proxy_settings":
                return "{}"
            if key == "rag_collection":
                return ""
            return None

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: NoKeyRepo())

    r = create_app().test_client().get("/v1/models", headers={NO_TEST_PROXY_AUTH_HEADER: "1"})
    assert r.status_code == 503
    data = r.get_json() or {}
    assert (data.get("error") or {}).get("type") == "server_configuration_error"
    assert (data.get("error") or {}).get("message") == "Chiron proxy API key is not configured"


@pytest.mark.fast
@pytest.mark.api
def test_v1_models_returns_401_when_proxy_api_key_missing() -> None:
    from api.http.rag_routes import create_app

    r = create_app().test_client().get("/v1/models", headers={NO_TEST_PROXY_AUTH_HEADER: "1"})
    assert r.status_code == 401
    data = r.get_json() or {}
    assert (data.get("error") or {}).get("type") == "authentication_error"
    assert (data.get("error") or {}).get("message") == "Invalid or missing API key"


@pytest.mark.fast
@pytest.mark.api
def test_v1_models_returns_401_when_proxy_api_key_invalid() -> None:
    from api.http.rag_routes import create_app

    r = create_app().test_client().get("/v1/models", headers={"Authorization": "Bearer wrong-key"})
    assert r.status_code == 401
    data = r.get_json() or {}
    assert (data.get("error") or {}).get("type") == "authentication_error"
    assert (data.get("error") or {}).get("message") == "Invalid or missing API key"


@pytest.mark.fast
@pytest.mark.api
def test_v1_models_accepts_bearer_proxy_api_key() -> None:
    from api.http.rag_routes import create_app

    r = create_app().test_client().get(
        "/v1/models",
        headers={"Authorization": f"Bearer {TEST_PROXY_API_KEY}"},
    )
    assert r.status_code == 200
    assert "data" in (r.get_json() or {})


@pytest.mark.fast
@pytest.mark.api
def test_v1_models_accepts_x_api_key_proxy_api_key() -> None:
    from api.http.rag_routes import create_app

    r = create_app().test_client().get("/v1/models", headers={"x-api-key": TEST_PROXY_API_KEY})
    assert r.status_code == 200
    assert "data" in (r.get_json() or {})


@pytest.mark.fast
@pytest.mark.api
def test_webui_reveal_proxy_api_key_returns_404_for_hash_only_legacy_key() -> None:
    from api.http.rag_routes import create_app

    client = create_app().test_client()
    status = client.get("/api/webui/llm-proxy/api-key").get_json() or {}
    assert status.get("configured") is True
    assert status.get("recoverable") is False

    r = client.post("/api/webui/llm-proxy/api-key/reveal")
    assert r.status_code == 404
    error = (r.get_json() or {}).get("error") or {}
    assert "not recoverable" in (error.get("message") or "")


@pytest.mark.fast
@pytest.mark.api
def test_webui_generate_proxy_api_key_returns_plaintext_once_and_enables_v1() -> None:
    from api.http.rag_routes import create_app

    client = create_app().test_client()
    generated = client.post("/api/webui/llm-proxy/api-key/generate").get_json() or {}
    key = generated.get("key")
    assert isinstance(key, str)
    assert key.startswith("chiron_sk_")
    assert generated.get("configured") is True
    assert generated.get("recoverable") is True
    assert generated.get("prefix")
    assert generated.get("created_at")
    assert "sha256" not in generated
    assert "secret" not in generated

    status = client.get("/api/webui/llm-proxy/api-key").get_json() or {}
    assert status.get("configured") is True
    assert "key" not in status
    assert "sha256" not in status
    assert "secret" not in status

    revealed = client.post("/api/webui/llm-proxy/api-key/reveal").get_json() or {}
    assert revealed.get("key") == key
    assert revealed.get("recoverable") is True
    assert "sha256" not in revealed
    assert "secret" not in revealed

    r = client.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200
    assert "data" in (r.get_json() or {})


@pytest.mark.fast
@pytest.mark.api
def test_webui_generated_proxy_api_key_accepts_x_api_key() -> None:
    from api.http.rag_routes import create_app

    client = create_app().test_client()
    generated = client.post("/api/webui/llm-proxy/api-key/generate").get_json() or {}
    key = generated["key"]

    r = client.get("/v1/models", headers={"x-api-key": key})
    assert r.status_code == 200
    assert "data" in (r.get_json() or {})


@pytest.mark.fast
@pytest.mark.api
def test_webui_regenerate_proxy_api_key_invalidates_old_key() -> None:
    from api.http.rag_routes import create_app

    client = create_app().test_client()
    first = client.post("/api/webui/llm-proxy/api-key/generate").get_json() or {}
    second = client.post("/api/webui/llm-proxy/api-key/generate").get_json() or {}
    assert first["key"] != second["key"]
    assert second.get("rotated_at")

    old_response = client.get("/v1/models", headers={"Authorization": f"Bearer {first['key']}"})
    assert old_response.status_code == 401

    new_response = client.get("/v1/models", headers={"Authorization": f"Bearer {second['key']}"})
    assert new_response.status_code == 200


@pytest.mark.fast
@pytest.mark.api
def test_webui_delete_proxy_api_key_closes_v1() -> None:
    from api.http.rag_routes import create_app

    client = create_app().test_client()
    generated = client.post("/api/webui/llm-proxy/api-key/generate").get_json() or {}
    assert generated.get("configured") is True

    deleted = client.delete("/api/webui/llm-proxy/api-key").get_json() or {}
    assert deleted.get("configured") is False

    r = client.get("/v1/models", headers={"Authorization": f"Bearer {generated['key']}"})
    assert r.status_code == 503
    assert ((r.get_json() or {}).get("error") or {}).get("type") == "server_configuration_error"


@pytest.mark.fast
@pytest.mark.api
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/v1/models", None),
        ("post", "/v1/chat/completions", {"model": "fake", "messages": []}),
        ("post", "/v1/messages", {"model": "fake", "messages": []}),
        ("post", "/v1/responses", {"model": "fake", "input": "hi"}),
        ("post", "/v1/files/apply-edit", {}),
        ("post", "/v1/external-docs/ingest", {}),
    ],
)
def test_v1_routes_share_proxy_api_key_middleware(method: str, path: str, body: dict[str, Any] | None) -> None:
    from api.http.rag_routes import create_app

    client = create_app().test_client()
    request_fn = getattr(client, method)
    kwargs: dict[str, Any] = {"headers": {NO_TEST_PROXY_AUTH_HEADER: "1"}}
    if body is not None:
        kwargs["json"] = body
    r = request_fn(path, **kwargs)
    assert r.status_code == 401
    assert ((r.get_json() or {}).get("error") or {}).get("type") == "authentication_error"


@pytest.mark.fast
@pytest.mark.api
def test_non_v1_routes_remain_reachable_without_proxy_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.rag_routes as rag_routes

    monkeypatch.setattr(
        rag_routes,
        "check_stack_health",
        lambda: SimpleNamespace(
            http_status=200,
            to_json_dict=lambda service: {"service": service, "status": "healthy"},
        ),
    )

    client = rag_routes.create_app().test_client()
    assert client.get("/health").status_code == 200
