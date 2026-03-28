"""
Light integration tests for HTTP endpoints (Flask test client).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _rag_routes_llm_proxy_app_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """/chat/completions requires saved proxy_model + prompt_name unless create_app uses system_prefix."""
    import json

    import api.http.rag_routes as rag_routes

    class _FakeRepo:
        def get_app_setting(self, key: str):
            if key == "proxy_model":
                return "fake-proxy-ollama-model"
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "rag_collection":
                return ""
            return None

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: _FakeRepo())


def test_health_endpoint() -> None:
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from api.http.rag_routes import create_app
    app = create_app()
    client = app.test_client()
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("status") == "ok"


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
    assert len(data["data"]) >= 1
    assert data["data"][0]["id"] == "rag-ollama"


def test_chat_completions_returns_tool_calls_when_edit_payload_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return (
                '{"file_path":"modules/webui_frontend/src/App.jsx",'
                '"range":{"start_line":283,"start_col":1,"end_line":293,"end_col":1},'
                '"new_text":"const tabs = [];"}'
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"))
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [{"role": "user", "content": "[@App.jsx (283:293)] Внеси это изменение в файл"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "apply_file_edit",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                            "required": ["path", "content"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    choice = data["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "apply_file_edit"


def test_chat_completions_overrides_none_tool_choice_for_file_edit_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import sys
    from pathlib import Path

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    test_file = Path(root) / "tests" / "_tmp_test.swift"
    if test_file.exists():
        test_file.unlink()
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("", encoding="utf-8")

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            tmp_path = str(test_file).replace("\\", "/")
            return (
                '{"file_path":"'+tmp_path+'",'
                '"mode":"edit",'
                '"new_text":"import UIKit\\n\\nclass SimpleViewController: UIViewController {}\\n"}'
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    file_uri = "file:///" + str(test_file).replace("\\", "/")
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [
                {
                    "role": "user",
                    "content": f"[@_tmp_test.swift]({file_uri}) Напиши простой пример UIViewController",
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "mode": {"type": "string"},
                                "display_description": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["path", "mode", "content"],
                        },
                    },
                },
            ],
            "tool_choice": "none",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    choice = data["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    # In real Zed sessions `save_file` is preferred when available for Swift,
    # but the minimal test tool list only exposes `edit_file`, so accept that.
    assert choice["message"]["tool_calls"][0]["function"]["name"] in ("edit_file", "save_file")
    tcalls = choice["message"]["tool_calls"][0]
    fn = tcalls["function"]
    args = __import__("json").loads(fn["arguments"])
    assert args["mode"] in ("overwrite", "create")
    assert args["mode"] == "overwrite"

    # Cleanup
    if test_file.exists():
        test_file.unlink()


def test_chat_completions_keeps_none_tool_choice_for_jsx(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return "No tool call expected for jsx when tool_choice is none."

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [
                {
                    "role": "user",
                    "content": "[@const.jsx](file:///C:/Users/Raylee/Desktop/const.jsx) add tabs",
                }
            ],
            "tools": [{"type": "function", "function": {"name": "edit_file", "parameters": {"type": "object"}}}],
            "tool_choice": "none",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    choice = data["choices"][0]
    assert choice["finish_reason"] == "stop"
    assert "tool_calls" not in choice["message"]


def test_chat_completions_preserves_mac_file_uri_in_tool_args(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import os
    import sys
    from types import SimpleNamespace

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    mac_uri = "file:///Users/alice/Projects/App/test.swift"

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            # Model may emit a relative path; proxy must prefer the user's file:/// URI.
            return '{"file_path":"test.swift","mode":"edit","new_text":"print(\\"hi\\")\\n"}'

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [{"role": "user", "content": f"Update this file [@test.swift]({mac_uri})"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "mode": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["path", "mode", "content"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    tc = data["choices"][0]["message"]["tool_calls"][0]
    args = json.loads(tc["function"]["arguments"])
    assert args["path"] == "/Users/alice/Projects/App/test.swift"


def test_chat_completions_stream_returns_tool_calls_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return (
                '{"file_path":"modules/webui_frontend/src/App.jsx",'
                '"range":{"start_line":283,"start_col":1,"end_line":293,"end_col":1},'
                '"new_text":"const tabs = [];"}'
            )

        def stream_chat(self, _messages, _model):
            yield "unused"

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"))
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "stream": True,
            "messages": [{"role": "user", "content": "[@App.jsx (283:293)] Внеси это изменение в файл"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "apply_file_edit",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                            "required": ["path", "content"],
                        },
                    },
                },
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "tool_calls" in body
    assert "\"finish_reason\": \"tool_calls\"" in body
    assert "\"name\": \"apply_file_edit\"" in body


def test_chat_completions_uses_client_tool_name_for_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return (
                '{"file_path":"modules/webui_frontend/src/App.jsx",'
                '"range":{"start_line":283,"start_col":1,"end_line":293,"end_col":1},'
                '"new_text":"const tabs = [];"}'
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"))
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [{"role": "user", "content": "[@App.jsx (283:293)] Внеси это изменение в файл"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "replace_in_file_range",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}, "replacement": {"type": "string"}},
                            "required": ["path", "replacement"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    tc = data["choices"][0]["message"]["tool_calls"][0]
    assert tc["function"]["name"] == "replace_in_file_range"


def test_chat_completions_adds_required_display_description(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return (
                '{"file_path":"modules/webui_frontend/src/App.jsx",'
                '"range":{"start_line":283,"start_col":1,"end_line":293,"end_col":1},'
                '"new_text":"const tabs = [];"}'
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"))
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [{"role": "user", "content": "Edit this range"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "parameters": {
                            "type": "object",
                            "required": ["display_description", "path", "mode"],
                            "properties": {
                                "display_description": {"type": "string"},
                                "path": {"type": "string"},
                                "mode": {"type": "string"},
                                "content": {"type": "string"},
                            },
                        },
                    },
                },
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    tc = data["choices"][0]["message"]["tool_calls"][0]
    assert tc["function"]["name"] == "edit_file"
    args = json.loads(tc["function"]["arguments"])
    assert args["display_description"]
    assert args["path"] == "modules/webui_frontend/src/App.jsx"
    assert args["mode"] == "edit"
    assert "file_path" not in args
    assert "content" in args and args["content"].strip()


def test_chat_completions_strict_mode_no_tool_call_without_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return "Just plain explanation, no JSON payload."

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"))
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [{"role": "user", "content": "[@App.jsx (283:293)] edit"}],
            "tools": [{"type": "function", "function": {"name": "edit_file", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["choices"][0]["finish_reason"] == "stop"
    assert "tool_calls" not in data["choices"][0]["message"]


def test_chat_completions_cline_style_schema_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return (
                '{"file_path":"modules/webui_frontend/src/App.jsx",'
                '"range":{"start_line":283,"start_col":1,"end_line":293,"end_col":1},'
                '"new_text":"const tabs = [];"}'
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"))
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [{"role": "user", "content": "Edit this range"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "replace_in_file_range",
                        "parameters": {
                            "type": "object",
                            "required": ["path", "replacement"],
                            "properties": {
                                "path": {"type": "string"},
                                "replacement": {"type": "string"},
                            },
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    tc = data["choices"][0]["message"]["tool_calls"][0]
    args = json.loads(tc["function"]["arguments"])
    assert set(args.keys()) == {"path", "replacement"}
    assert args["path"] == "modules/webui_frontend/src/App.jsx"
    assert args["replacement"] == "const tabs = [];"


def test_stream_tool_mode_returns_plain_text_when_no_tool_json(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return "Normal assistant answer without JSON."

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"))
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "stream": True,
            "messages": [{"role": "user", "content": "edit this"}],
            "tools": [{"type": "function", "function": {"name": "edit_file", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Normal assistant answer without JSON." in body
    assert "\"finish_reason\": \"stop\"" in body


def test_chat_completions_after_tool_success_uses_plain_completion_not_second_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the latest turn is a successful tool result, do not force another tool JSON round."""
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    captured: list[list[dict[str, object]]] = []

    class FakeChatClient:
        def chat(self, messages, _model, stream=False, options=None):
            captured.append([m for m in messages if isinstance(m, dict)])
            return "Edit applied as requested."

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"))
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    messages = [
        {"role": "user", "content": "move testing tab first"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "edit_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Successfully edited App.jsx."},
    ]
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "stream": False,
            "messages": messages,
            "tools": [{"type": "function", "function": {"name": "edit_file", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    choice = data["choices"][0]
    assert choice["finish_reason"] == "stop"
    assert choice["message"].get("tool_calls") in (None, [])
    assert "Edit applied" in (choice["message"].get("content") or "")
    from llm_proxy.tool_helpers import _POST_TOOL_SUCCESS_SYSTEM as _post_tool_ok_sys

    assert captured and any(
        _post_tool_ok_sys[:30] in str(m.get("content", "")) for batch in captured for m in batch
    )


def test_chat_completions_after_tool_success_still_emits_tool_call_for_new_file_edit_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return (
                '{"file_path":"C:/Users/Raylee/Desktop/test.swift",'
                '"mode":"overwrite",'
                '"new_text":"import Foundation\\nprint(\\"Hello\\")\\n"}'
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    messages = [
        {"role": "user", "content": "Old edit"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "edit_file", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "1 clean."},
        {
            "role": "user",
            "content": "Напиши Hello World на Swift 5 [@test.swift](file:///C:/Users/Raylee/Desktop/test.swift)",
        },
    ]
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "stream": False,
            "messages": messages,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "save_file",
                        "parameters": {
                            "type": "object",
                            "required": ["paths"],
                            "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "mode": {"type": "string"},
                                "display_description": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["path", "mode", "content"],
                        },
                    },
                },
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    choice = data["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "edit_file"


def test_stream_tool_mode_skips_tool_call_when_edit_body_is_only_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return (
                '{"file_path":"modules/webui_frontend/src/App.jsx",'
                '"mode":"edit",'
                '"new_text":"  \\n\\t  "}'
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"))
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "stream": True,
            "messages": [{"role": "user", "content": "edit App.jsx"}],
            "tools": [{"type": "function", "function": {"name": "edit_file", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "\"finish_reason\": \"tool_calls\"" not in body
    assert "\"finish_reason\": \"stop\"" in body


def test_apply_edit_endpoint_replaces_text_range() -> None:
    import os
    import sys
    from pathlib import Path

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from api.http.rag_routes import create_app

    test_file = Path(root) / "tests" / "_tmp_apply_edit.txt"
    test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
    try:
        app = create_app()
        client = app.test_client()
        r = client.post(
            "/v1/files/apply-edit",
            json={
                "file_path": "tests/_tmp_apply_edit.txt",
                "range": {"start_line": 2, "start_col": 1, "end_line": 2, "end_col": 6},
                "new_text": "line2_updated",
            },
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        updated = test_file.read_text(encoding="utf-8")
        assert "line2_updated" in updated
    finally:
        if test_file.exists():
            test_file.unlink()


def test_chat_completions_builds_save_file_paths_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    from types import SimpleNamespace

    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return json.dumps(
                {
                    "path": "build_and_run.bat",
                    "new_text": "@echo off\ncall build_app.bat",
                    "mode": "create",
                }
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    # Keep RAG context and Ollama messages minimal; tool args are built from tool JSON only.
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [{"role": "user", "content": "Create build_and_run.bat"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "save_file",
                        "parameters": {
                            "type": "object",
                            "required": ["paths", "mode"],
                            "properties": {
                                "paths": {"type": "array"},
                                "mode": {"type": "string"},
                            },
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    tool_call = data["choices"][0]["message"]["tool_calls"][0]
    args = json.loads(tool_call["function"]["arguments"])
    assert tool_call["function"]["name"] == "save_file"
    assert args["mode"] == "create"
    assert isinstance(args["paths"], list)
    assert args["paths"][0]["path"] == "build_and_run.bat"
    assert "@echo off" in args["paths"][0]["content"]


def test_chat_completions_builds_save_file_paths_as_strings_when_schema_requires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    from types import SimpleNamespace

    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return json.dumps(
                {
                    "path": "Desktop/test.swift",
                    "new_text": "import UIKit\nprint(\"Hello\")\n",
                    "mode": "overwrite",
                }
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [{"role": "user", "content": "Write Hello World to test.swift"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "save_file",
                        "parameters": {
                            "type": "object",
                            "required": ["paths", "mode"],
                            "properties": {
                                "paths": {"type": "array", "items": {"type": "string"}},
                                "mode": {"type": "string"},
                                "content": {"type": "string"},
                            },
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    tool_call = data["choices"][0]["message"]["tool_calls"][0]
    args = json.loads(tool_call["function"]["arguments"])
    assert tool_call["function"]["name"] == "save_file"
    assert args["mode"] == "overwrite"
    assert isinstance(args["paths"], list)
    assert isinstance(args["paths"][0], str)


def test_chat_completions_does_not_choose_save_file_without_content_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    from types import SimpleNamespace

    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            # Model returns a relative-ish path; proxy should prefer user absolute path.
            return json.dumps(
                {
                    "path": "Desktop/test.swift",
                    "new_text": "import Foundation\\nprint(\\\"Hello\\\")\\n",
                    "mode": "overwrite",
                }
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [
                {
                    "role": "user",
                    "content": "Напиши Hello World на Swift 5 [@test.swift](file:///C:/Users/Raylee/Desktop/test.swift)",
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "save_file",
                        "parameters": {
                            "type": "object",
                            "required": ["paths"],
                            "properties": {
                                # Critical: no `content` property here.
                                "paths": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "mode": {"type": "string"},
                                "display_description": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["path", "mode", "content"],
                        },
                    },
                },
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    tc = data["choices"][0]["message"]["tool_calls"][0]
    # Must not choose save_file without content support; should choose edit_file.
    assert tc["function"]["name"] == "edit_file"
    args = json.loads(tc["function"]["arguments"])
    assert args.get("path") == "C:/Users/Raylee/Desktop/test.swift"
    assert "content" in args and "Hello" in args["content"]


def test_chat_completions_sanitizes_display_description(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    from types import SimpleNamespace

    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return json.dumps(
                {
                    "file_path": "C:/Users/Raylee/AI/test.swift",
                    "mode": "edit",
                    "new_text": "let array = [1, 2, 3]\nprint(array)\n",
                }
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "messages": [
                {
                    "role": "user",
                    "content": "[@test.swift (1:3)](file:///C:/Users/Raylee/AI/test.swift#L1:3) сожми массив до 3 <context>\nThe following items were attached by the user.\n<files>\n```swift C:/Users/Raylee/AI/test.swift\nlet array=[1,2,3]\n```\n</files>\n</context>",
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "mode": {"type": "string"},
                                "display_description": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["path", "mode", "display_description", "content"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    tc = data["choices"][0]["message"]["tool_calls"][0]
    args = json.loads(tc["function"]["arguments"])
    dd = args.get("display_description", "")
    assert "<context>" not in dd
    assert "The following items were attached by the user" not in dd
    assert len(dd) <= 180


def test_chat_completions_blocks_repeated_no_edit_recursion(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):
            return '{"file_path":"C:/Users/Raylee/AI/test.swift","mode":"edit","new_text":"let array = [1,2,3]\\n"}'

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    first_messages = [
        {"role": "user", "content": "[@test.swift (1:3)](file:///C:/Users/Raylee/AI/test.swift#L1:3) сожми массив до 3"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "edit_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "No edits were made."},
        {"role": "user", "content": "[@test.swift (1:3)](file:///C:/Users/Raylee/AI/test.swift#L1:3) сожми массив до 3"},
    ]
    second_messages = [
        {"role": "user", "content": "[@test.swift (1:3)](file:///C:/Users/Raylee/AI/test.swift#L1:3) сожми массив до 3"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_2", "type": "function", "function": {"name": "edit_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_2", "content": "No edits were made."},
        {"role": "user", "content": "[@test.swift (1:3)](file:///C:/Users/Raylee/AI/test.swift#L1:3) сожми массив до 3"},
    ]
    r1 = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "stream": False,
            "messages": first_messages,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "stream": False,
            "messages": second_messages,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r2.status_code == 200
    data = r2.get_json()
    choice = data["choices"][0]
    assert choice["finish_reason"] == "stop"
    assert "No edits were made" in (choice["message"]["content"] or "")


def test_trailing_noop_after_success_does_not_block_noop_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a real diff, a final 'No edits were made.' must not hit noop_retry_blocked (nor loop tools)."""
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, messages, _model, stream=False, options=None):
            for m in messages:
                if not isinstance(m, dict):
                    continue
                c = m.get("content") or ""
                if (
                    m.get("role") == "system"
                    and isinstance(c, str)
                    and "short plain-text confirmation" in c
                ):
                    return "Файл уже обновлён."
            return '{"file_path":"C:/Users/Raylee/AI/test.swift","mode":"edit","new_text":"noop\\n"}'

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    success_body = "Status: Completed\n```swift\nlet array = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]\n```\n"
    msgs = [
        {
            "role": "user",
            "content": "[@test.swift (1:5)](file:///C:/Users/Raylee/AI/test.swift#L1:5) расширь массив",
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "edit_file", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "No edits were made."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "edit_file", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c2", "content": success_body},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c3", "type": "function", "function": {"name": "edit_file", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c3", "content": "No edits were made."},
        {
            "role": "user",
            "content": "[@test.swift (1:5)](file:///C:/Users/Raylee/AI/test.swift#L1:5) расширь массив",
        },
    ]

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "stream": False,
            "messages": msgs,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    choice = data["choices"][0]
    content = choice["message"].get("content") or ""
    assert "repeatedly" not in content.lower()
    assert "expand the selected range" not in content.lower()
    assert choice.get("finish_reason") == "stop"
    assert "обновл" in content.lower() or "already" in content.lower()


def test_chat_completions_internal_full_file_retry_on_fragment_with_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Partial new_text with full <files> range triggers a second in-proxy chat before one tool call."""
    import json
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    # Fewer non-empty lines than the 3-line <files> excerpt so partial-file guard fires.
    partial = '    print("Number \\(element)")\n'
    full = (
        "let array = [1, 2, 3]\n"
        "print(array)\n"
        "helper()\n"
        "for element in array {\n"
        '    print("Number \\(element)")\n'
        "}\n"
    )

    class FakeChatClient:
        def __init__(self) -> None:
            self.chat_calls = 0

        def chat(self, _messages, _model, stream=False, options=None):
            self.chat_calls += 1
            if self.chat_calls == 1:
                return json.dumps(
                    {
                        "file_path": "C:/Users/Raylee/AI/test.swift",
                        "mode": "edit",
                        "new_text": partial,
                    }
                )
            return json.dumps(
                {
                    "file_path": "C:/Users/Raylee/AI/test.swift",
                    "mode": "edit",
                    "new_text": full,
                }
            )

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "x"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    user_content = (
        "[@test.swift](file:///C:/Users/Raylee/AI/test.swift) foreach each element\n"
        "<context>\nThe following items were attached by the user.\n<files>\n"
        "```swift C:/Users/Raylee/AI/test.swift\n"
        "let array = [1, 2, 3]\n"
        "print(array)\n"
        "helper()\n"
        "```\n</files>\n</context>"
    )

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-ollama",
            "stream": False,
            "messages": [{"role": "user", "content": user_content}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "mode": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["path", "mode", "content"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    assert fake_deps.chat_client.chat_calls == 2
    data = r.get_json()
    tc = data["choices"][0]["message"]["tool_calls"][0]
    args = json.loads(tc["function"]["arguments"])
    body = args.get("content") or args.get("new_text") or ""
    assert "let array = [1, 2, 3]" in body
    assert "for element in array" in body


def test_build_tool_arguments_drops_empty_body_strings_then_syncs() -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from llm_proxy.tool_helpers import _build_tool_arguments

    args = _build_tool_arguments(
        selected_tool_name="edit_file",
        selected_tool={
            "function": {
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "mode": {"type": "string"},
                        "content": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    "required": ["path", "mode", "content", "new_text"],
                }
            }
        },
        edit_payload={
            "file_path": "C:/Users/Raylee/AI/test.swift",
            "mode": "edit",
            "new_text": "ONLYLINE\n",
            "content": "",
        },
        user_query="[@test.swift](file:///C:/Users/Raylee/AI/test.swift) ok",
    )
    assert args.get("content") == "ONLYLINE\n"
    assert args.get("new_text") == "ONLYLINE\n"
    for k in ("content", "new_text", "replacement"):
        if k in args:
            assert str(args[k]).strip() != ""


def test_chat_completions_400_when_proxy_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import api.http.rag_routes as rag_routes

    class Repo:
        def get_app_setting(self, key: str):
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return ""
            return None

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={"model": "rag-ollama", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 400
    assert "model" in (r.get_json() or {}).get("error", "").lower()


def test_chat_completions_400_when_prompt_template_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import api.http.rag_routes as rag_routes

    class Repo:
        def get_app_setting(self, key: str):
            if key == "proxy_settings":
                return json.dumps({"prompt_name": ""})
            if key == "proxy_model":
                return "real-ollama-model"
            return None

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={"model": "rag-ollama", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 400
    err = (r.get_json() or {}).get("error", "")
    assert "prompt" in err.lower() or "template" in err.lower()


def test_chat_completions_accepts_direct_ollama_model_without_proxy_model_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client may pass a concrete Ollama model id; proxy_model DB row is not required for that path."""
    import json
    from types import SimpleNamespace

    import api.http.rag_routes as rag_routes

    class Repo:
        def get_app_setting(self, key: str):
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return ""
            return None

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())

    class FakeChatClient:
        def chat(self, _messages, model, stream=False, options=None):
            return "ok"

        def stream_chat(self, _messages, _model):
            yield ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="unused",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=FakeChatClient(),
    )
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda *args, **kwargs: ([{"role": "user", "content": "hi"}], "llama3"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={"model": "llama3:latest", "messages": [{"role": "user", "content": "hi"}], "skip_rag": True},
    )
    assert r.status_code == 200
