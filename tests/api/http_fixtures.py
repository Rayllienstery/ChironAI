"""Shared fixtures and helpers for HTTP integration tests (Phase 1 test split)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from flask.testing import FlaskClient
from werkzeug.datastructures import Headers

TEST_PROXY_API_KEY = "test-chiron-proxy-key"
NO_TEST_PROXY_AUTH_HEADER = "X-Test-Skip-Chiron-Auth"
TEST_PROXY_API_KEY_SETTING = "llm_proxy_api_key"
TEST_PROXY_API_KEY_SETTING_VALUE = json.dumps(
    {
        "sha256": hashlib.sha256(TEST_PROXY_API_KEY.encode("utf-8")).hexdigest(),
        "prefix": TEST_PROXY_API_KEY[:20],
        "created_at": "2026-05-04T00:00:00Z",
        "rotated_at": None,
    }
)


def test_proxy_api_key_setting(key: str) -> str | None:
    if key == TEST_PROXY_API_KEY_SETTING:
        return TEST_PROXY_API_KEY_SETTING_VALUE
    return None


def set_extensions_app_state(
    app: Any,
    *,
    service: Any | None = None,
    runtime: Any | None = None,
) -> None:
    from api.http.extensions_service_access import set_extensions_runtime, set_extensions_service

    set_extensions_service(app, service)
    if runtime is not None:
        set_extensions_runtime(app, runtime)


def webui_blueprint_client():
    from flask import Flask

    import api.http.webui_routes as webui_routes

    app = Flask(__name__)
    app.register_blueprint(webui_routes.webui_bp)
    return app.test_client()


class OllamaShimChatClient:
    """
    Wraps test doubles whose ``chat()`` returns legacy JSON-in-text edit payloads.
    Exposes ``chat_api`` / ``chat_api_stream_final`` expected by the native Ollama tools path.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.chat(*args, **kwargs)

    def stream_chat(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.stream_chat(*args, **kwargs)

    def chat_api(self, body: dict[str, Any]) -> dict[str, Any]:
        from llm_proxy.tool_helpers import (
            _build_tool_arguments,
            _extract_edit_from_response,
            _get_tool_by_name,
            _select_edit_tool_name,
            _tool_args_have_substantive_body,
        )

        messages = body.get("messages") or []
        tools = body.get("tools") or []
        raw = self._inner.chat(messages, body.get("model"), stream=False, options=None)
        raw = raw or ""
        if not tools:
            return {"message": {"role": "assistant", "content": str(raw)}}
        uq = ""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                c = m.get("content")
                uq = c if isinstance(c, str) else ""
                break
        edit = _extract_edit_from_response(raw)
        sel = _select_edit_tool_name(tools, uq)
        if edit and sel:
            tdef = _get_tool_by_name(tools, sel)
            args = _build_tool_arguments(
                selected_tool_name=sel,
                selected_tool=tdef,
                edit_payload=edit,
                user_query=uq,
            )
            if _tool_args_have_substantive_body(sel, args):
                return {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {"type": "function", "function": {"name": sel, "arguments": args}},
                        ],
                    }
                }
        return {"message": {"role": "assistant", "content": str(raw)}}

    def chat_api_stream_final(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.chat_api({**body, "stream": False})

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@pytest.fixture(autouse=True)
def rag_routes_llm_proxy_app_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """/chat/completions requires saved proxy_model + prompt_name unless create_app uses system_prefix."""
    import api.http.rag_routes as rag_routes
    import api.http.webui_routes as webui_routes
    from llm_interactor import ExtensionManager

    original_open = FlaskClient.open

    def open_with_proxy_auth(self, *args: Any, **kwargs: Any):
        path = kwargs.get("path")
        if path is None and args and isinstance(args[0], str):
            path = args[0]
        if isinstance(path, str) and (path == "/v1" or path.startswith("/v1/")):
            headers = Headers(kwargs.get("headers") or {})
            if headers.get(NO_TEST_PROXY_AUTH_HEADER):
                del headers[NO_TEST_PROXY_AUTH_HEADER]
            elif not headers.get("Authorization") and not headers.get("x-api-key"):
                headers["Authorization"] = f"Bearer {TEST_PROXY_API_KEY}"
            kwargs["headers"] = headers
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(FlaskClient, "open", open_with_proxy_auth)

    class FakeRepo:
        def __init__(self, include_api_key: bool = True) -> None:
            self.app_settings = {
                "proxy_model": "fake-proxy-ollama-model",
                "proxy_settings": json.dumps({"prompt_name": "system_senior_ios_assistant_v1"}),
                "rag_collection": "",
            }
            if include_api_key:
                self.app_settings[TEST_PROXY_API_KEY_SETTING] = TEST_PROXY_API_KEY_SETTING_VALUE

        def get_app_setting(self, key: str):
            return self.app_settings.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.app_settings[key] = value

        def delete_app_setting(self, key: str) -> None:
            self.app_settings.pop(key, None)

    fake_repo = FakeRepo()

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: fake_repo)
    monkeypatch.setattr(webui_routes, "get_settings_repository", lambda: fake_repo)
    monkeypatch.setattr(ExtensionManager, "start_background_bootstrap", lambda self: None)
