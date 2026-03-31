"""Tests for Proxy V2 Flask app (isolated wiring mocks)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from proxy_v2 import create_pass_proxy_v2_app
from proxy_v2.contracts import ProxyV2Wiring


def _bridge_msgs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "user":
            out.append({"role": "user", "content": str(m.get("content") or "")})
    return out or [{"role": "user", "content": ""}]


@pytest.fixture
def wiring_no_pin() -> ProxyV2Wiring:
    def chat_api(body: dict[str, Any]) -> dict[str, Any]:
        return {"message": {"role": "assistant", "content": "hello"}, "done": True}

    def stream_final(body: dict[str, Any]) -> dict[str, Any]:
        return chat_api({**body, "stream": False})

    def iter_stream(body: dict[str, Any]):
        yield ("content", "h")
        yield ("content", "i")

    return ProxyV2Wiring(
        get_ollama_chat_url=lambda: "http://127.0.0.1:11434/api/chat",
        get_pinned_model=lambda: "",
        get_default_chat_options=lambda: {},
        openai_messages_to_ollama=_bridge_msgs,
        ollama_tools_from_openai=lambda t: t,
        ollama_message_to_openai_assistant=lambda m: {"role": "assistant", "content": m.get("content")},
        openai_finish_reason_from_ollama=lambda _m: "stop",
        chat_api=chat_api,
        iter_chat_stream_openai_parts=iter_stream,
        chat_api_stream_final=stream_final,
        host_apply_file_edit=None,
        host_external_docs_ingest=None,
    )


@pytest.fixture
def app(wiring_no_pin: ProxyV2Wiring):
    return create_pass_proxy_v2_app(wiring_no_pin)


@pytest.fixture
def client(app):
    return app.test_client()


def test_health(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json().get("status") == "ok"


def test_v1_models_empty_when_no_pin(client) -> None:
    r = client.get("/v1/models")
    assert r.status_code == 200
    assert r.get_json().get("data") == []


def test_chat_completions_requires_model(client) -> None:
    r = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 400


def test_chat_completions_ok(client) -> None:
    r = client.post(
        "/v1/chat/completions",
        json={"model": "test:latest", "messages": [{"role": "user", "content": "x"}], "stream": False},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("choices")


def test_chat_completions_trace_has_client_and_upstream_payload(wiring_no_pin, client) -> None:
    from proxy_v2.trace_store import get_current_trace

    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "test:latest",
            "messages": [{"role": "user", "content": "hello-trace"}],
            "stream": False,
        },
    )
    assert r.status_code == 200
    tr = get_current_trace()
    assert tr is not None
    openai_body = (tr.get("request") or {}).get("openai_body") or {}
    assert openai_body.get("messages")
    assert any("hello-trace" in str(m.get("content", "")) for m in openai_body.get("messages", []))
    upstream_body = (tr.get("upstream") or {}).get("body") or {}
    assert upstream_body.get("messages")
    assert any("hello-trace" in str(m.get("content", "")) for m in upstream_body.get("messages", []))
    assert (tr.get("upstream") or {}).get("url")


def test_completions_requires_prompt(client) -> None:
    r = client.post("/v1/completions", json={"model": "m", "stream": False})
    assert r.status_code == 400


@patch("proxy_v2.ollama_forward.requests.get")
def test_forward_tags(mock_get, wiring_no_pin) -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"models": [{"name": "a"}]}
    mock_get.return_value = mock_resp
    app = create_pass_proxy_v2_app(wiring_no_pin)
    client = app.test_client()
    r = client.get("/api/tags")
    assert r.status_code == 200, r.get_json()
    assert mock_get.called


def test_apply_edit_503_without_delegate(wiring_no_pin, client) -> None:
    r = client.post("/v1/files/apply-edit", json={})
    assert r.status_code == 503


def test_models_lists_pin() -> None:
    w = ProxyV2Wiring(
        get_ollama_chat_url=lambda: "http://127.0.0.1:11434/api/chat",
        get_pinned_model=lambda: "mypin",
        get_default_chat_options=lambda: {},
        openai_messages_to_ollama=_bridge_msgs,
        ollama_tools_from_openai=lambda t: t,
        ollama_message_to_openai_assistant=lambda m: m,
        openai_finish_reason_from_ollama=lambda _m: "stop",
        chat_api=lambda b: {"message": {"role": "assistant", "content": "x"}},
        iter_chat_stream_openai_parts=lambda b: iter(()),
        chat_api_stream_final=lambda b: {"message": {"role": "assistant", "content": "x"}},
    )
    app = create_pass_proxy_v2_app(w)
    r = app.test_client().get("/v1/models")
    data = r.get_json().get("data") or []
    assert len(data) == 1
    assert data[0].get("id") == "mypin"
