"""
Light integration tests for HTTP endpoints (Flask test client).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


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
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "apply_file_edit"


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
            "tools": [{"type": "function", "function": {"name": "apply_file_edit", "parameters": {"type": "object"}}}],
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
                    "function": {"name": "replace_in_file_range", "parameters": {"type": "object"}},
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
                            "properties": {"display_description": {"type": "string"}, "path": {"type": "string"}},
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
    assert args["display_description"]
    assert args["path"] == "modules/webui_frontend/src/App.jsx"
    assert args["mode"] == "edit"
    assert "file_path" not in args
    assert "new_text" not in args


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
