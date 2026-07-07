"""Chat completions and /v1 responses integration tests (split from test_http_endpoints.py)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.api.http_fixtures import (
    OllamaShimChatClient as _OllamaShimChatClient,
)
from tests.api.http_fixtures import (
    patch_rag_answer_params as _patch_rag_answer_params,
)
from tests.api.http_fixtures import (
    test_proxy_api_key_setting as _test_proxy_api_key_setting,
)


def test_chat_completions_chironai_autocomplete_uses_same_prompt_template_as_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logical id ChironAI-Autocomplete uses the same prompt template as Worker and maps to the AC Ollama tag."""
    import json
    from types import SimpleNamespace

    import rag_service.application.params as rag_params

    import api.http.rag_routes as rag_routes

    monkeypatch.setenv("LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL", "fast-ac-model")

    class Repo:
        def get_app_setting(self, key: str):
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return ""
            return _test_proxy_api_key_setting(key)

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())

    class FakeChatClient:
        def chat(self, _messages, model, stream=False, options=None):  # noqa
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
    fc = FakeChatClient()
    fc._url = "http://ollama.test:11434/api/chat"
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=_OllamaShimChatClient(fc),
    )
    _fake_rag_params = lambda **kwargs: (fake_params, fake_deps)
    monkeypatch.setattr(rag_params, "get_rag_answer_params", _fake_rag_params)
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", _fake_rag_params)
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
        lambda *args, **kwargs: ([{"role": "user", "content": "hi"}], "fast-ac-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={"model": "ChironAI-Autocomplete", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200
    body = r.get_json() or {}
    assert body.get("model") == "fast-ac-model"

    r_root = client.post(
        "/v1",
        json={"model": "ChironAI-Autocomplete", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r_root.status_code == 200
    assert (r_root.get_json() or {}).get("model") == "fast-ac-model"

    r_legacy = client.post(
        "/v1",
        json={"model": "ChironAI-Autocomplete", "prompt": "def foo():"},
    )
    assert r_legacy.status_code == 404
    assert ((r_legacy.get_json() or {}).get("error") or {}).get("type") == "unsupported_endpoint"


def test_chat_completions_returns_tool_calls_when_edit_payload_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
            return (
                '{"file_path":"CoreModules/CoreUI/src/App.jsx",'
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
            "messages": [{"role": "user", "content": "[@App.jsx (283:293)] Apply this change to the file"}],
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


def test_chat_completions_native_tools_passthrough_skips_argument_normalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native tool_calls arguments are forwarded without path/range normalization (passthrough-only)."""
    import json
    import os
    import sys
    from pathlib import Path

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    test_file = Path(root) / "tests" / "_tmp_native_tool_passthrough.swift"
    try:
        if test_file.exists():
            test_file.unlink()
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("let array = [1, 2, 3]\nprint(array)\n", encoding="utf-8")
        file_uri = "file:///" + str(test_file).replace("\\", "/")

        class Repo:
            def get_app_setting(self, key: str):
                if key == "proxy_model":
                    return "fake-proxy-ollama-model"
                if key == "proxy_settings":
                    return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
                if key == "rag_collection":
                    return ""
                return _test_proxy_api_key_setting(key)

        monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())

        class NativeMessyOllamaClient:
            def chat_api(self, body: dict[str, Any]) -> dict[str, Any]:
                return {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "edit_file",
                                    "arguments": {
                                        "path": "test.swift",
                                        "mode": "overwrite",
                                        "content": '    print("x")\n',
                                    },
                                },
                            }
                        ],
                    }
                }

            def chat(self, *_a: Any, **_k: Any) -> str:
                return ""

            def stream_chat(self, *_a: Any, **_k: Any) -> Any:
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
            chat_client=NativeMessyOllamaClient(),
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

        def _prepare_native(request: Any, *_a: Any, **kw: Any) -> tuple[list[dict[str, Any]], str]:
            from rag_service.infrastructure.openai_ollama_tool_bridge import openai_messages_to_ollama

            if kw.get("native_tools"):
                oll = openai_messages_to_ollama([m for m in request.messages if isinstance(m, dict)])
                return [{"role": "system", "content": "system"}] + oll, "fake-model"
            return ([{"role": "user", "content": "x"}], "fake-model")

        monkeypatch.setattr(rag_routes, "prepare_ollama_messages", _prepare_native)
        monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

        app = rag_routes.create_app()
        client = app.test_client()
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "fake-proxy-ollama-model",
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"[@_tmp_native_tool_passthrough.swift (1:2)]({file_uri}) foreach each element"
                        ),
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
        assert r.status_code == 200, r.get_data(as_text=True)
        data = r.get_json() or {}
        choice = data["choices"][0]
        assert choice["finish_reason"] == "tool_calls"
        args = json.loads(choice["message"]["tool_calls"][0]["function"]["arguments"])
        assert args.get("path") == "test.swift"
        assert args.get("mode") == "overwrite"
    finally:
        if test_file.exists():
            test_file.unlink()


def test_chat_completions_native_tools_recovers_dsml_tool_call_from_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.http.rag_routes as rag_routes

    class Repo:
        def get_app_setting(self, key: str):
            if key == "proxy_model":
                return "fake-proxy-ollama-model"
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "rag_collection":
                return ""
            return _test_proxy_api_key_setting(key)

    class DsmlOllamaClient:
        _default_options = {"temperature": 0.0}

        def chat_api(self, _body: dict[str, Any]) -> dict[str, Any]:
            return {
                "message": {
                    "role": "assistant",
                    "thinking": (
                        "~197KB. Let me inspect it.\n\n"
                        "<｜DSML｜tool_calls>\n"
                        "<｜DSML｜invoke name=\"shell\">\n"
                        "<｜DSML｜parameter name=\"command\" string=\"false\">"
                        "[\"powershell.exe\", \"-Command\", \"Get-ChildItem -Path api\\\\http\\\\webui_routes.py\"]"
                        "</｜DSML｜parameter>\n"
                        "</｜DSML｜invoke>\n"
                        "</｜DSML｜tool_calls>"
                    ),
                    "content": "",
                },
                "done_reason": "stop",
            }

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-proxy-ollama-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=DsmlOllamaClient(),
    )

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "messages": [{"role": "user", "content": "reduce webui_routes.py"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "shell",
                        "parameters": {
                            "type": "object",
                            "properties": {"command": {"type": "array", "items": {"type": "string"}}},
                            "required": ["command"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )

    assert r.status_code == 200, r.get_data(as_text=True)
    data = r.get_json() or {}
    choice = data["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    message = choice["message"]
    assert message["content"] is None
    assert message["reasoning_content"] == "~197KB. Let me inspect it."
    assert "model returned reasoning without final answer" not in json.dumps(data)
    tc = message["tool_calls"][0]
    assert tc["function"]["name"] == "shell"
    args = json.loads(tc["function"]["arguments"])
    assert args["command"] == ["powershell.exe", "-Command", "Get-ChildItem -Path api\\http\\webui_routes.py"]

    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    assert "native_tool_calls_recovered_from_text" in (trace.get("warnings") or [])
    assert (trace.get("response") or {}).get("tool_calls_recovered_from_text") is True
    assert (trace.get("response") or {}).get("tool_calls_count") == 1


def test_chat_completions_respects_none_tool_choice_for_swift_file_edit_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Swift edit intent with tool_choice none returns assistant text, not synthetic tool_calls."""
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
            "messages": [
                {
                    "role": "user",
                    "content": f"[@_tmp_test.swift]({file_uri}) Write a simple UIViewController example",
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
    assert choice["finish_reason"] == "stop"
    assert not choice["message"].get("tool_calls")
    content = choice["message"].get("content") or ""
    assert "UIKit" in content or "file_path" in content

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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
            "messages": [
                {
                    "role": "user",
                    "content": "[@const.jsx](file:///C:/Users/Example/Desktop/const.jsx) add tabs",
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
        lambda *args, **kwargs: (
            [{"role": "user", "content": f"Update this file [@test.swift]({mac_uri})"}],
            "fake-model",
        ),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
            return (
                '{"file_path":"CoreModules/CoreUI/src/App.jsx",'
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
            "stream": True,
            "messages": [{"role": "user", "content": "[@App.jsx (283:293)] Apply this change to the file"}],
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
            return (
                '{"file_path":"CoreModules/CoreUI/src/App.jsx",'
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
            "messages": [{"role": "user", "content": "[@App.jsx (283:293)] Apply this change to the file"}],
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
            return (
                '{"file_path":"CoreModules/CoreUI/src/App.jsx",'
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
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
    assert args["path"] == "CoreModules/CoreUI/src/App.jsx"
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
            return (
                '{"file_path":"CoreModules/CoreUI/src/App.jsx",'
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
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
    assert args["path"] == "CoreModules/CoreUI/src/App.jsx"
    assert args["replacement"] == "const tabs = [];"


def test_stream_tool_mode_returns_plain_text_when_no_tool_json(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
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
        def chat(self, messages, _model, stream=False, options=None):  # noqa
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
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
    assert captured


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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
            return (
                '{"file_path":"C:/Users/Example/Desktop/test.swift",'
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "content": "Write Hello World in Swift 5 [@test.swift](file:///C:/Users/Example/Desktop/test.swift)",
        },
    ]
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
            return (
                '{"file_path":"CoreModules/CoreUI/src/App.jsx",'
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
        lambda *args, **kwargs: (
            [
                {
                    "role": "user",
                    "content": "Write Hello World in Swift 5 [@test.swift](file:///C:/Users/Example/Desktop/test.swift)",
                }
            ],
            "fake-model",
        ),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "messages": [
                {
                    "role": "user",
                    "content": "Write Hello World in Swift 5 [@test.swift](file:///C:/Users/Example/Desktop/test.swift)",
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
    assert args.get("path") == "C:/Users/Example/Desktop/test.swift"
    assert "content" in args and "Hello" in args["content"]


def test_chat_completions_sanitizes_display_description(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    from types import SimpleNamespace

    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
            return json.dumps(
                {
                    "file_path": "C:/Users/Example/AI/test.swift",
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
            "model": "fake-proxy-ollama-model",
            "messages": [
                {
                    "role": "user",
                    "content": "[@test.swift (1:3)](file:///C:/Users/Example/AI/test.swift#L1:3) shrink the array to 3 <context>\nThe following items were attached by the user.\n<files>\n```swift C:/Users/Example/AI/test.swift\nlet array=[1,2,3]\n```\n</files>\n</context>",
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


def test_trailing_noop_after_success_does_not_block_noop_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a successful edit, a trailing noop tool result still allows a normal follow-up completion."""
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.http.rag_routes as rag_routes

    class FakeChatClient:
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
            return '{"file_path":"C:/Users/Example/AI/test.swift","mode":"edit","new_text":"noop\\n"}'

        def stream_chat(self, _messages, _model):
            yield ""

    class TrailingNoopShim(_OllamaShimChatClient):
        def chat_api(self, body: dict[str, Any]) -> dict[str, Any]:
            msgs = body.get("messages") or []
            if any(
                "Status: Completed" in str(m.get("content", ""))
                for m in msgs
                if isinstance(m, dict)
            ):
                return {"message": {"role": "assistant", "content": "The file is already updated."}}
            return super().chat_api(body)

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
        chat_client=TrailingNoopShim(FakeChatClient()),
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

    def _prepare_trailing(request: Any, *_a: Any, **kw: Any) -> tuple[list[dict[str, Any]], str]:
        from rag_service.infrastructure.openai_ollama_tool_bridge import openai_messages_to_ollama

        if kw.get("native_tools"):
            oll = openai_messages_to_ollama([m for m in request.messages if isinstance(m, dict)])
            return [{"role": "system", "content": ""}] + oll, "fake-model"
        return ([{"role": "user", "content": "x"}], "fake-model")

    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", _prepare_trailing)
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    success_body = "Status: Completed\n```swift\nlet array = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]\n```\n"
    msgs = [
        {
            "role": "user",
            "content": "[@test.swift (1:5)](file:///C:/Users/Example/AI/test.swift#L1:5) expand the array",
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
            "content": "[@test.swift (1:5)](file:///C:/Users/Example/AI/test.swift#L1:5) expand the array",
        },
    ]

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
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
    assert "updated" in content.lower() or "already" in content.lower()


def test_chat_completions_text_tool_path_single_chat_no_full_file_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON tool path uses the first model response only (no hidden full-file retry chat)."""
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

        def chat(self, _messages, _model, stream=False, options=None):  # noqa
            self.chat_calls += 1
            if self.chat_calls == 1:
                return json.dumps(
                    {
                        "file_path": "C:/Users/Example/AI/test.swift",
                        "mode": "edit",
                        "new_text": partial,
                    }
                )
            return json.dumps(
                {
                    "file_path": "C:/Users/Example/AI/test.swift",
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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
        "[@test.swift](file:///C:/Users/Example/AI/test.swift) foreach each element\n"
        "<context>\nThe following items were attached by the user.\n<files>\n"
        "```swift C:/Users/Example/AI/test.swift\n"
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
            "model": "fake-proxy-ollama-model",
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
    assert fake_deps.chat_client.chat_calls == 1
    data = r.get_json()
    tc = data["choices"][0]["message"]["tool_calls"][0]
    args = json.loads(tc["function"]["arguments"])
    body = args.get("content") or args.get("new_text") or ""
    assert body.strip() == partial.strip()


def test_build_tool_arguments_overwrite_becomes_edit_when_range_and_file_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """overwrite + range on existing file would truncate in some IDEs; force edit."""
    import os
    import sys
    from pathlib import Path

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    monkeypatch.setattr("llm_proxy.workspace._workspace_root_fn", lambda: Path(root))
    from llm_proxy.tool_helpers import _build_tool_arguments
    tmp = Path(root) / "tests" / "_tmp_overwrite_range_edit.swift"
    try:
        tmp.write_text("a\nb\nc\n", encoding="utf-8")
        uri = tmp.as_uri()
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
                        },
                        "required": ["path", "mode", "content"],
                    },
                },
            },
            edit_payload={
                "path": "bogus.swift",
                "mode": "overwrite",
                "content": "x\n",
                "range": {"start_line": 1, "start_col": 1, "end_line": 2, "end_col": 1},
            },
            user_query=f"[@x]({uri}) fix",
        )
        assert args.get("mode") == "edit"
        assert str(tmp.resolve()) in str(args.get("path") or "") or tmp.name in str(args.get("path") or "")
    finally:
        if tmp.exists():
            tmp.unlink()


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
            "file_path": "C:/Users/Example/AI/test.swift",
            "mode": "edit",
            "new_text": "ONLYLINE\n",
            "content": "",
        },
        user_query="[@test.swift](file:///C:/Users/Example/AI/test.swift) ok",
    )
    assert args.get("content") == "ONLYLINE\n"
    assert args.get("new_text") == "ONLYLINE\n"
    for k in ("content", "new_text", "replacement"):
        if k in args:
            assert str(args[k]).strip() != ""


def test_chat_completions_400_when_prompt_template_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import api.http.rag_routes as rag_routes

    class Repo:
        def get_app_setting(self, key: str):
            if key == "proxy_settings":
                return json.dumps({"prompt_name": ""})
            if key == "proxy_model":
                return "real-ollama-model"
            return _test_proxy_api_key_setting(key)

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={"model": "fake-proxy-ollama-model", "messages": [{"role": "user", "content": "hi"}]},
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
            return _test_proxy_api_key_setting(key)

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())

    class FakeChatClient:
        def chat(self, _messages, model, stream=False, options=None):  # noqa
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
        chat_client=_OllamaShimChatClient(FakeChatClient()),
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


def test_chat_completions_collection_params_call_is_compatible_without_prompt_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import api.http.rag_routes as rag_routes

    seen: dict[str, Any] = {}

    def fake_get_rag_answer_params(*, webui_dir=None, collection_name=None):
        seen["webui_dir"] = webui_dir
        seen["collection_name"] = collection_name
        fake_params = SimpleNamespace(
            system_prefix="",
            system_suffix="",
            context_chunk_chars=500,
            context_total_chars=2000,
            confidence_threshold=0.0,
            model_name="unused",
            log_preview_chars=200,
        )

        class FakeChatClient:
            def chat(self, _messages, model, stream=False, options=None):  # noqa
                return "ok"

            def stream_chat(self, _messages, _model):
                yield ""

        fake_deps = SimpleNamespace(
            rag_repo=object(),
            embed_provider=object(),
            rerank_client=None,
            chat_client=_OllamaShimChatClient(FakeChatClient()),
        )
        return fake_params, fake_deps

    monkeypatch.setattr(rag_routes, "get_rag_answer_params", fake_get_rag_answer_params)
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
    r = app.test_client().post(
        "/v1/chat/completions",
        json={
            "model": "llama3:latest",
            "collection_name": "docs",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    assert seen.get("collection_name") == "docs"


def test_v1_blueprint_unhandled_exception_is_logged_for_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    import api.http.rag_routes as rag_routes

    logged: list[tuple[str, str, str | None]] = []

    def fake_log_webui_error(source: str, error: Exception, extra: dict[str, Any]) -> None:
        logged.append((source, type(error).__name__, (extra or {}).get("stage")))

    monkeypatch.setattr(rag_routes, "log_webui_error", fake_log_webui_error)

    def raising_chat_completions(_wiring, body_override=None):
        raise RuntimeError("forced crash")

    monkeypatch.setattr(v1_blueprint, "run_chat_completions", raising_chat_completions)

    app = rag_routes.create_app()
    r = app.test_client().post(
        "/v1/chat/completions",
        json={"model": "llama3:latest", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 500
    assert "forced crash" in str((r.get_json() or {}).get("error", ""))
    assert logged
    source, err_type, stage = logged[0]
    assert source == "rag_routes.v1_unhandled"
    assert err_type == "RuntimeError"
    assert stage == "unhandled_exception"


def test_v1_chat_completions_smoke_supports_two_turn_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify, request

    import api.http.rag_routes as rag_routes

    calls: list[dict[str, Any]] = []

    def fake_chat_completions(_wiring, body_override=None):
        payload = body_override if isinstance(body_override, dict) else (request.get_json(force=True, silent=True) or {})
        calls.append(dict(payload or {}))
        messages = list((payload or {}).get("messages") or [])
        last_user = ""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                last_user = str(m.get("content") or "")
                break
        return jsonify(
            {
                "id": "chatcmpl_tools",
                "object": "chat.completion",
                "created": 789,
                "model": "Hard-worker",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": f"echo:{last_user}"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )

    monkeypatch.setattr(v1_blueprint, "run_chat_completions", fake_chat_completions)

    app = rag_routes.create_app()
    client = app.test_client()
    first = client.post(
        "/v1/chat/completions",
        json={
            "model": "Hard-worker",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )
    assert first.status_code == 200
    assert "echo:Hi" in str((first.get_json() or {}).get("choices", [{}])[0].get("message", {}).get("content", ""))

    second = client.post(
        "/v1/chat/completions",
        json={
            "model": "Hard-worker",
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "echo:Hi"},
                {"role": "user", "content": "Explain this codebase"},
            ],
            "tools": [{"type": "function", "function": {"name": "apply_file_edit", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )
    assert second.status_code == 200
    assert "echo:Explain this codebase" in str(
        (second.get_json() or {}).get("choices", [{}])[0].get("message", {}).get("content", "")
    )
    assert len(calls) == 2
    assert (calls[1].get("tools") or [])[0].get("type") == "function"


def test_v1_responses_route_maps_to_chat_and_returns_response_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify

    import api.http.rag_routes as rag_routes

    captured: dict[str, Any] = {}

    def fake_chat_completions(_wiring, body_override=None):
        captured["body_override"] = body_override
        return jsonify(
            {
                "id": "chatcmpl_test",
                "object": "chat.completion",
                "created": 123,
                "model": "Hard-worker",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello from RAG"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        )

    monkeypatch.setattr(v1_blueprint, "run_chat_completions", fake_chat_completions)

    app = rag_routes.create_app()
    r = app.test_client().post("/v1/responses", json={"model": "Hard-worker", "input": "Hi"})
    assert r.status_code == 200
    payload = r.get_json() or {}
    assert payload.get("object") == "response"
    assert payload.get("status") == "completed"
    assert payload.get("output_text") == "Hello from RAG"
    usage = payload.get("usage") or {}
    assert usage.get("input_tokens") == 10
    assert usage.get("output_tokens") == 5
    msgs = (captured.get("body_override") or {}).get("messages") or []
    assert msgs and msgs[0].get("role") == "user"
    assert msgs[0].get("content") == "Hi"


def test_v1_responses_route_maps_input_image_to_chat_multipart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify

    import api.http.rag_routes as rag_routes

    png_b64 = "aW1hZ2UtYnl0ZXM="
    data_url = f"data:image/png;base64,{png_b64}"
    captured: dict[str, Any] = {}

    def fake_chat_completions(_wiring, body_override=None):
        captured["body_override"] = body_override
        return jsonify(
            {
                "id": "chatcmpl_test",
                "object": "chat.completion",
                "created": 123,
                "model": "Hard-worker",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "icon ok"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        )

    monkeypatch.setattr(v1_blueprint, "run_chat_completions", fake_chat_completions)

    app = rag_routes.create_app()
    r = app.test_client().post(
        "/v1/responses",
        json={
            "model": "Hard-worker",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "what is on the icon"},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
        },
    )
    assert r.status_code == 200
    msgs = (captured.get("body_override") or {}).get("messages") or []
    assert len(msgs) == 1
    content = msgs[0].get("content")
    assert isinstance(content, list)
    assert any(
        isinstance(p, dict)
        and p.get("type") == "image_url"
        and (p.get("image_url") or {}).get("url") == data_url
        for p in content
    )


def test_v1_responses_streaming_maps_input_image_to_chat_multipart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify

    import api.http.rag_routes as rag_routes

    png_b64 = "aW1hZ2UtYnl0ZXM="
    data_url = f"data:image/png;base64,{png_b64}"
    captured: dict[str, Any] = {}

    def fake_chat_completions(_wiring, body_override=None):
        captured["body_override"] = body_override
        return jsonify(
            {
                "id": "chatcmpl_stream_vision",
                "object": "chat.completion",
                "created": 123,
                "model": "Hard-worker",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "stream vision ok"}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        )

    monkeypatch.setattr(v1_blueprint, "run_chat_completions", fake_chat_completions)

    app = rag_routes.create_app()
    r = app.test_client().post(
        "/v1/responses",
        json={
            "model": "Hard-worker",
            "stream": True,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "what is on the icon"},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
        },
    )
    assert r.status_code == 200
    assert "text/event-stream" in (r.content_type or "")
    payload = r.get_data(as_text=True)
    assert "response.completed" in payload
    assert "stream vision ok" in payload

    body_override = captured.get("body_override") or {}
    trace_meta = body_override.get("_proxy_trace_meta") or {}
    assert trace_meta.get("responses_client_stream") is True
    assert body_override.get("stream") is False
    msgs = body_override.get("messages") or []
    assert len(msgs) == 1
    content = msgs[0].get("content")
    assert isinstance(content, list)
    assert any(
        isinstance(p, dict)
        and p.get("type") == "image_url"
        and (p.get("image_url") or {}).get("url") == data_url
        for p in content
    )


def test_v1_responses_tools_normalizer_maps_local_shell_and_custom_to_function() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    tools, diag = v1_blueprint._responses_normalize_tools(
        [
            {"type": "local_shell"},
            {"type": "custom", "name": "fetch_docs", "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}}},
            {"type": "function", "function": {"name": "apply_file_edit", "parameters": {"type": "object"}}},
        ]
    )
    names = [str((((t or {}).get("function") or {}).get("name") or "")) for t in tools]
    assert "shell" in names
    assert "fetch_docs" in names
    assert "apply_file_edit" in names
    assert diag.get("tools_count_raw") == 3
    assert diag.get("tools_count_normalized") == 3
    assert "local_shell->function" in (diag.get("tools_types_normalized") or [])
    assert "custom->function" in (diag.get("tools_types_normalized") or [])


def test_v1_responses_tools_normalizer_drops_unsupported_types() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    tools, diag = v1_blueprint._responses_normalize_tools(
        [
            {"type": "mcp_server"},
            {"type": "image_generation"},
            {"type": "unknown_custom_tool_xyz"},
        ]
    )
    assert tools == []
    assert diag.get("tools_count_raw") == 3
    assert diag.get("tools_count_normalized") == 0
    dropped = set(diag.get("tools_types_dropped") or [])
    assert {"mcp_server", "image_generation", "unknown_custom_tool_xyz"}.issubset(dropped)


def test_v1_responses_tools_normalizer_maps_responses_builtin_tools_to_functions() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    tools, diag = v1_blueprint._responses_normalize_tools(
        [
            {"type": "web_search"},
            {"type": "file_search"},
            {"type": "computer_use"},
            {"type": "shell"},
        ]
    )
    names = sorted(str(((t or {}).get("function") or {}).get("name") or "") for t in tools)
    assert names == ["computer_use", "file_search", "shell", "web_search"]
    assert diag.get("tools_count_raw") == 4
    assert diag.get("tools_count_normalized") == 4


def test_v1_responses_tools_normalizer_accepts_flat_function_tools() -> None:
    """Some Responses clients send ``type:function`` with ``name``/``parameters`` at top level (no ``function`` dict)."""
    import llm_proxy.v1_blueprint as v1_blueprint

    tools, diag = v1_blueprint._responses_normalize_tools(
        [
            {"type": "function", "name": "apply_patch", "description": "patch", "parameters": {"type": "object"}},
            {"type": "function", "function": {"name": "shell", "parameters": {"type": "object"}}},
            {"type": "web_search"},
        ]
    )
    names = {str(((t or {}).get("function") or {}).get("name") or "") for t in tools}
    assert names == {"apply_patch", "shell", "web_search"}
    assert diag.get("tools_count_raw") == 3
    assert diag.get("tools_count_normalized") == 3
    assert (diag.get("tools_types_dropped") or []) == []


def test_v1_responses_tool_choice_flat_function_name() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    body, _stream, _diag = v1_blueprint._responses_request_to_openai_chat_body(
        {
            "model": "Hard-worker",
            "input": "x",
            "tools": [{"type": "function", "name": "foo", "parameters": {"type": "object"}}],
            "tool_choice": {"type": "function", "name": "foo"},
        }
    )
    assert body.get("tool_choice") == {"type": "function", "function": {"name": "foo"}}


def test_v1_responses_tool_choice_web_search_maps_to_function() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    body, _stream, diag = v1_blueprint._responses_request_to_openai_chat_body(
        {
            "model": "Hard-worker",
            "input": "hi",
            "tools": [{"type": "web_search"}],
            "tool_choice": {"type": "web_search"},
        }
    )
    assert (body.get("tool_choice") or {}).get("type") == "function"
    assert ((body.get("tool_choice") or {}).get("function") or {}).get("name") == "web_search"
    assert diag.get("tool_choice_normalized") == {"type": "function", "function": {"name": "web_search"}}


def test_responses_request_to_openai_body_includes_proxy_trace_meta() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    body, stream, _diag = v1_blueprint._responses_request_to_openai_chat_body(
        {"model": "Hard-worker", "input": "hi", "stream": True}
    )
    assert stream is True
    assert body.get("_proxy_trace_meta") == {
        "proxy_v1_route": "/v1/responses",
        "responses_client_stream": True,
    }


def test_responses_sse_payload_output_item_done_includes_full_message_item() -> None:
    import json

    import llm_proxy.v1_blueprint as v1_blueprint

    msg_id = "msg_sse_full_item"
    out = {
        "id": "resp_sse_msg",
        "object": "response",
        "model": "Hard-worker",
        "output": [
            {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "Hello assistant", "annotations": []}],
            }
        ],
        "output_text": "Hello assistant",
    }
    resp = v1_blueprint._responses_sse_payload(out)
    payload = resp.get_data(as_text=True)
    cur_event: str | None = None
    for line in payload.split("\n"):
        if line.startswith("event: "):
            cur_event = line[len("event: ") :].strip()
            continue
        if line.startswith("data: ") and line.strip() != "data: [DONE]" and cur_event == "response.output_item.done":
            data = json.loads(line[len("data: ") :])
            item = data.get("item") or {}
            if item.get("type") == "message":
                assert item.get("id") == msg_id
                assert item.get("content")
                assert "Hello assistant" in json.dumps(item)
                return
    raise AssertionError("message output_item.done with content not found")


def test_responses_sse_payload_message_added_initializes_empty_content() -> None:
    import json

    import llm_proxy.v1_blueprint as v1_blueprint

    out = {
        "id": "resp_sse_added_msg",
        "object": "response",
        "model": "Hard-worker",
        "output": [
            {
                "id": "msg_sse_added",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "Hello", "annotations": []}],
            }
        ],
        "output_text": "Hello",
    }
    resp = v1_blueprint._responses_sse_payload(out)
    cur_event: str | None = None
    for line in resp.get_data(as_text=True).split("\n"):
        if line.startswith("event: "):
            cur_event = line[len("event: ") :].strip()
            continue
        if line.startswith("data: ") and cur_event == "response.output_item.added":
            data = json.loads(line[len("data: ") :])
            item = data.get("item") or {}
            if item.get("type") == "message":
                assert item.get("content") == []
                return
    raise AssertionError("message output_item.added event not found")


def test_responses_sse_payload_emits_function_call_stream_events() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    out = {
        "id": "resp_testfc",
        "object": "response",
        "model": "Hard-worker",
        "output": [
            {
                "id": "call_fc1",
                "type": "function_call",
                "status": "completed",
                "name": "shell",
                "arguments": '{"command":"ls"}',
                "call_id": "call_fc1",
            }
        ],
        "output_text": "",
    }
    resp = v1_blueprint._responses_sse_payload(out)
    payload = resp.get_data(as_text=True)
    assert "response.output_item.added" in payload
    assert "function_call" in payload
    assert "response.completed" in payload
    assert "call_fc1" in payload


def test_v1_responses_tool_choice_normalized_after_tools_mapping() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    body, _stream, diag = v1_blueprint._responses_request_to_openai_chat_body(
        {
            "model": "Hard-worker",
            "input": "hi",
            "tools": [{"type": "local_shell"}],
            "tool_choice": {"type": "local_shell"},
        }
    )
    assert (body.get("tool_choice") or {}).get("type") == "function"
    assert ((body.get("tool_choice") or {}).get("function") or {}).get("name") == "shell"
    assert diag.get("tool_choice_normalized") == {"type": "function", "function": {"name": "shell"}}


def test_v1_responses_route_maps_local_shell_to_function_tool_for_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify

    import api.http.rag_routes as rag_routes

    captured: dict[str, Any] = {}

    def fake_chat_completions(_wiring, body_override=None):
        captured["body_override"] = body_override
        return jsonify(
            {
                "id": "chatcmpl_tool",
                "object": "chat.completion",
                "created": 10,
                "model": "Hard-worker",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )

    monkeypatch.setattr(v1_blueprint, "run_chat_completions", fake_chat_completions)

    app = rag_routes.create_app()
    r = app.test_client().post(
        "/v1/responses",
        json={
            "model": "Hard-worker",
            "input": "Explain this codebase",
            "tools": [{"type": "local_shell"}],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    body = captured.get("body_override") or {}
    tools = body.get("tools") or []
    assert len(tools) == 1
    assert tools[0].get("type") == "function"
    assert ((tools[0].get("function") or {}).get("name")) == "shell"
    assert body.get("tools_count_raw") == 1
    assert body.get("tools_count_normalized") == 1


def test_v1_responses_followup_with_function_call_output_uses_previous_response_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify

    import api.http.rag_routes as rag_routes

    v1_blueprint._RESPONSES_HISTORY.clear()
    v1_blueprint._RESPONSES_CHAIN_IDS.clear()
    calls: list[dict[str, Any]] = []

    def fake_chat_completions(_wiring, body_override=None):
        body = dict(body_override or {})
        calls.append(body)
        if len(calls) == 1:
            return jsonify(
                {
                    "id": "chatcmpl_first",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "Hard-worker",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {"name": "shell", "arguments": "{\"command\":\"ls\"}"},
                                    }
                                ],
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                }
            )
        return jsonify(
            {
                "id": "chatcmpl_second",
                "object": "chat.completion",
                "created": 2,
                "model": "Hard-worker",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "done"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            }
        )

    monkeypatch.setattr(v1_blueprint, "run_chat_completions", fake_chat_completions)

    app = rag_routes.create_app()
    client = app.test_client()
    first = client.post(
        "/v1/responses",
        json={
            "model": "Hard-worker",
            "input": "list files",
            "tools": [{"type": "local_shell"}],
            "tool_choice": "auto",
        },
    )
    assert first.status_code == 200
    first_id = str((first.get_json() or {}).get("id") or "")
    assert first_id.startswith("resp_")

    second = client.post(
        "/v1/responses",
        json={
            "model": "Hard-worker",
            "previous_response_id": first_id,
            "input": [
                {"type": "function_call_output", "call_id": "call_1", "output": "file1\nfile2"},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "continue"}]},
            ],
        },
    )
    assert second.status_code == 200
    assert len(calls) == 2
    second_messages = calls[1].get("messages") or []
    has_prior_assistant_tool_call = any(
        isinstance(m, dict) and m.get("role") == "assistant" and isinstance(m.get("tool_calls"), list)
        for m in second_messages
    )
    has_tool_output = any(
        isinstance(m, dict) and m.get("role") == "tool" and m.get("tool_call_id") == "call_1"
        for m in second_messages
    )
    assert has_prior_assistant_tool_call
    assert has_tool_output
    first_meta = calls[0].get("_proxy_trace_meta") or {}
    second_meta = calls[1].get("_proxy_trace_meta") or {}
    assert str(first_meta.get("trace_chain_id") or "").startswith("responses:")
    assert second_meta.get("trace_chain_id") == first_meta.get("trace_chain_id")


def test_v1_responses_input_parses_function_call_output_id_aliases() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    msgs = v1_blueprint._responses_input_to_openai_messages(
        [
            {"type": "function_call_output", "tool_callid": "call_alias_1", "output": {"ok": True}},
            {"type": "function_call_output", "id": "call_alias_2", "output": "done"},
        ]
    )
    assert msgs[0]["role"] == "tool"
    assert msgs[0]["tool_call_id"] == "call_alias_1"
    assert msgs[1]["role"] == "tool"
    assert msgs[1]["tool_call_id"] == "call_alias_2"


def test_v1_responses_input_preserves_function_call_output_name_aliases() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    msgs = v1_blueprint._responses_input_to_openai_messages(
        [
            {"type": "function_call_output", "call_id": "call_1", "name": "shell", "output": "ok"},
            {"type": "function_call_output", "call_id": "call_2", "tool_name": "web_search", "output": "ok"},
        ]
    )
    assert msgs[0]["role"] == "tool"
    assert msgs[0]["tool_call_id"] == "call_1"
    assert msgs[0]["name"] == "shell"
    assert msgs[0]["tool_name"] == "shell"
    assert msgs[1]["role"] == "tool"
    assert msgs[1]["tool_call_id"] == "call_2"
    assert msgs[1]["name"] == "web_search"
    assert msgs[1]["tool_name"] == "web_search"


def test_v1_responses_output_function_call_uses_stable_id_call_id_when_missing() -> None:
    import llm_proxy.v1_blueprint as v1_blueprint

    out, _text = v1_blueprint._chat_message_to_responses_output_items(
        {
            "role": "assistant",
            "tool_calls": [{"type": "function", "function": {"name": "shell", "arguments": "{\"command\":\"dir\"}"}}],
        }
    )
    assert out
    fc = out[0]
    assert fc["type"] == "function_call"
    assert isinstance(fc.get("id"), str) and fc["id"].startswith("call_")
    assert fc["call_id"] == fc["id"]


def test_native_tools_preflight_recovers_tool_name_and_sets_name_alias() -> None:
    import llm_proxy.chat_completions as cc

    out, diag = cc._preflight_native_tool_messages(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "shell", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        ]
    )
    tool_msg = out[1]
    assert tool_msg["tool_name"] == "shell"
    assert tool_msg["name"] == "shell"
    assert diag.get("tool_message_name_recovered_heuristic_count") == 1
    assert (diag.get("tool_message_name_recovered_heuristic_sources") or {}).get("call_id_map") == 1


def test_tool_loop_limit_final_message_names_real_stop_reason() -> None:
    import llm_proxy.chat_completions_handler as handler

    msg = handler._tool_loop_limit_final_message(
        {
            "request": {
                "tool_loop_limit_reached": True,
                "tool_loop_stats": {"rounds": 25, "dominant_tool": "shell"},
            }
        }
    )

    assert "max_agent_steps limit reached after 25 tool rounds (shell)" in msg
    assert "model returned reasoning without final answer" not in msg


def test_sse_tool_calls_payload_preserves_thought_signature_aliases() -> None:
    import llm_proxy.chat_completions as cc

    payload = cc._sse_tool_calls_payload(
        [
            {
                "id": "call_1",
                "type": "function",
                "extra_content": {"google": {"thought_signature": "sig_1"}},
                "function": {"name": "glob", "arguments": "{\"pattern\":\"*\"}"},
            }
        ]
    )
    assert payload
    tc = payload[0]
    assert tc["id"] == "call_1"
    assert tc["call_id"] == "call_1"
    assert (tc.get("function") or {}).get("thought_signature") == "sig_1"
    assert ((tc.get("extra_content") or {}).get("google") or {}).get("thought_signature") == "sig_1"


def test_interpolate_native_tools_for_gemini_preserves_names_and_normalizes_schema() -> None:
    import llm_proxy.chat_completions as cc

    tools = [
        {
            "type": "function",
            "function": {
                "name": "edit",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "nullable": True},
                        "mode": {"type": "string", "enum": ["overwrite", {"bad": True}]},
                        "body": {"oneOf": [{"type": "string"}, {"type": "null"}]},
                    },
                    "required": ["path", "missing", 7],
                    "oneOf": [{"type": "object"}],
                },
            },
        },
        {
            "type": "function",
            "name": "read",
            "description": "Read file",
            "parameters": {"type": "array", "items": [{"type": "string"}, {"type": "number"}]},
        },
        {"type": "web_search", "name": "web_search"},
    ]
    out, diag = cc._interpolate_native_tools_for_gemini(
        tools,
        model_name="gemini-3-flash-preview:cloud",
    )

    assert out
    assert diag.get("gemini_tool_interpolation_enabled") is True
    assert int(diag.get("gemini_tool_schema_normalized_count") or 0) >= 1
    assert int(diag.get("gemini_tool_schema_relaxed_count") or 0) >= 1

    by_name = {
        str(((t.get("function") or {}).get("name")) or ""): t
        for t in out
        if isinstance(t, dict) and isinstance(t.get("function"), dict)
    }
    assert "edit" in by_name
    assert "read" in by_name
    edit_params = by_name["edit"]["function"]["parameters"]
    assert edit_params["type"] == "object"
    assert edit_params["required"] == ["path"]
    assert "oneOf" not in edit_params
    assert edit_params["properties"]["path"]["type"] == "string"
    assert "nullable" not in edit_params["properties"]["path"]
    read_params = by_name["read"]["function"]["parameters"]
    assert read_params["type"] == "array"
    assert read_params["items"]["type"] == "string"
    assert any(isinstance(t, dict) and t.get("type") == "web_search" for t in out)


def test_interpolate_native_tools_for_non_gemini_is_noop() -> None:
    import llm_proxy.chat_completions as cc

    tools = [{"type": "function", "function": {"name": "shell", "parameters": {"type": "object"}}}]
    out, diag = cc._interpolate_native_tools_for_gemini(tools, model_name="qwen2.5-coder:latest")
    assert out is tools
    assert diag == {}





def test_is_gemini_model_name_accepts_google_family_variants() -> None:
    import llm_proxy.chat_completions as cc

    positives = [
        "gemini-3-flash-preview:cloud",
        "google/gemini-2.5-pro",
        "models/gemini-2.5-flash",
        "gemini-exp-1206",
        "vendor/models/gemini-2.0-flash-thinking",
    ]
    for model in positives:
        assert cc._is_gemini_model_name(model) is True


def test_is_gemini_model_name_rejects_non_gemini_families() -> None:
    import llm_proxy.chat_completions as cc

    negatives = [
        "",
        "gemma-3-27b-it",
        "google/gemma-3n-e2b",
        "qwen2.5-coder:latest",
        "gpt-4o",
    ]
    for model in negatives:
        assert cc._is_gemini_model_name(model) is False

def test_preflight_native_tool_messages_gemini_recovers_signature_and_name_from_db(
    tmp_path: Path,
) -> None:
    import llm_proxy.chat_completions as cc

    db_path = str(tmp_path / "webui.db")
    upserted = cc._gemini_tool_state_upsert_many(
        db_path,
        rows=[
            {
                "call_id": "call_1",
                "model": "gemini-3-flash-preview:cloud",
                "function_name": "glob",
                "thought_signature": "sig_db_1",
                "trace_id": "trace-seed",
            }
        ],
    )
    assert upserted == 1

    messages = [
        {
            "role": "assistant",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"arguments": "{\"pattern\":\"*\"}"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
    ]
    out, diag = cc._preflight_native_tool_messages(
        messages,
        model_name="gemini-3-flash-preview:cloud",
        trace_id="trace-1",
        db_path=db_path,
    )

    tc = out[0]["tool_calls"][0]
    fn = tc["function"]
    assert fn["name"] == "glob"
    assert fn["thought_signature"] == "sig_db_1"
    assert ((tc.get("extra_content") or {}).get("google") or {}).get("thought_signature") == "sig_db_1"
    assert out[1]["tool_name"] == "glob"
    assert out[1]["name"] == "glob"
    assert int(diag.get("gemini_signature_recovered_from_db_count") or 0) >= 1
    assert int(diag.get("gemini_tool_name_recovered_from_db_count") or 0) >= 1


def test_preflight_native_tool_messages_gemini_falls_back_to_sentinel_signature(
    tmp_path: Path,
) -> None:
    import llm_proxy.chat_completions as cc

    out, diag = cc._preflight_native_tool_messages(
        [
            {
                "role": "assistant",
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "glob", "arguments": "{}"}}],
            }
        ],
        model_name="gemini-3-flash-preview:cloud",
        trace_id="trace-2",
        db_path=str(tmp_path / "webui.db"),
    )
    tc = out[0]["tool_calls"][0]
    assert tc["function"]["thought_signature"] == "skip_thought_signature_validator"
    assert int(diag.get("gemini_signature_fallback_sentinel_count") or 0) >= 1


def test_resolve_trace_chain_id_prefers_client_request_id() -> None:
    import llm_proxy.chat_completions as cc

    chain_id, source = cc._resolve_trace_chain_id(
        client_request_id="client-chain-1",
        proxy_trace_meta={"incoming_request_id": "header-chain-1"},
    )
    assert chain_id == "client-chain-1"
    assert source == "client_request_id"


def test_resolve_trace_chain_id_uses_incoming_meta_when_client_id_missing() -> None:
    import llm_proxy.chat_completions as cc

    chain_id, source = cc._resolve_trace_chain_id(
        client_request_id="",
        proxy_trace_meta={"incoming_request_id": "header-chain-1"},
    )
    assert chain_id == "header-chain-1"
    assert source == "incoming_request_id"


def test_resolve_trace_chain_id_prefers_explicit_proxy_trace_meta() -> None:
    import llm_proxy.chat_completions as cc

    chain_id, source = cc._resolve_trace_chain_id(
        client_request_id="",
        proxy_trace_meta={"incoming_request_id": "header-chain-1", "trace_chain_id": "responses-chain-1"},
    )
    assert chain_id == "responses-chain-1"
    assert source == "trace_chain_id"


def test_v1_chat_completions_route_injects_incoming_request_id_into_proxy_trace_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify

    import api.http.rag_routes as rag_routes

    captured: dict[str, Any] = {}

    def fake_chat_completions(_wiring, body_override=None):
        captured["body_override"] = dict(body_override or {})
        return jsonify(
            {
                "id": "chatcmpl_trace_meta",
                "object": "chat.completion",
                "created": 10,
                "model": "Hard-worker",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )

    monkeypatch.setattr(v1_blueprint, "run_chat_completions", fake_chat_completions)

    app = rag_routes.create_app()
    r = app.test_client().post(
        "/v1/chat/completions",
        headers={"x-request-id": "hdr-chain-xyz"},
        json={
            "model": "Hard-worker",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    meta = (captured.get("body_override") or {}).get("_proxy_trace_meta") or {}
    assert meta.get("proxy_v1_route") == "/v1/chat/completions"
    assert meta.get("incoming_request_id") == "hdr-chain-xyz"


def test_v1_responses_route_injects_incoming_request_id_into_proxy_trace_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify

    import api.http.rag_routes as rag_routes

    captured: dict[str, Any] = {}

    def fake_chat_completions(_wiring, body_override=None):
        captured["body_override"] = dict(body_override or {})
        return jsonify(
            {
                "id": "chatcmpl_trace_meta",
                "object": "chat.completion",
                "created": 10,
                "model": "Hard-worker",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )

    monkeypatch.setattr(v1_blueprint, "run_chat_completions", fake_chat_completions)

    app = rag_routes.create_app()
    r = app.test_client().post(
        "/v1/responses",
        headers={"x-trace-id": "trace-chain-abc"},
        json={
            "model": "Hard-worker",
            "input": "hi",
        },
    )
    assert r.status_code == 200
    meta = (captured.get("body_override") or {}).get("_proxy_trace_meta") or {}
    assert meta.get("proxy_v1_route") == "/v1/responses"
    assert meta.get("incoming_request_id") == "trace-chain-abc"


def test_native_tools_stream_trace_includes_tokens_estimates_and_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.http.rag_routes as rag_routes

    class NativeStreamChatClient:
        def iter_chat_api_stream_events(self, _payload: dict[str, Any]):
            yield ("content_delta", "done")
            yield ("done", {"done_reason": "stop", "eval_count": 12, "prompt_eval_count": 4})

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

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
        chat_client=NativeStreamChatClient(),
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

    def _prepare_native(request: Any, *_a: Any, **kw: Any) -> tuple[list[dict[str, Any]], str]:
        from rag_service.infrastructure.openai_ollama_tool_bridge import openai_messages_to_ollama

        if kw.get("native_tools"):
            oll = openai_messages_to_ollama([m for m in request.messages if isinstance(m, dict)])
            return [{"role": "system", "content": "system"}] + oll, "fake-model"
        return ([{"role": "user", "content": "x"}], "fake-model")

    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", _prepare_native)
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    _ = r.get_data(as_text=True)

    cur = client.get("/api/webui/proxy-trace/current")
    assert cur.status_code == 200
    trace = (cur.get_json() or {}).get("trace") or {}
    oll_tok = ((trace.get("ollama") or {}).get("tokens_estimates") or {})
    resp = trace.get("response") or {}
    assert int(oll_tok.get("prompt_tokens_estimated") or 0) >= 1
    assert int(oll_tok.get("completion_tokens_estimated") or 0) >= 1
    assert int(oll_tok.get("total_tokens_estimated") or 0) >= 1
    assert int(resp.get("latency_ms") or 0) >= 0


def test_streaming_vision_request_preserves_native_tools_when_model_supports_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.chat_completions_handler as handler

    import api.http.rag_routes as rag_routes

    class VisionStreamChatClient:
        def __init__(self) -> None:
            self._url = "http://fake-ollama/api/chat"
            self.payloads: list[dict[str, Any]] = []

        def iter_chat_api_stream_events(self, payload: dict[str, Any]):
            self.payloads.append(payload)
            yield ("content_delta", "vision ok")
            yield ("done", {"done_reason": "stop", "eval_count": 6, "prompt_eval_count": 3})

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    chat_client = VisionStreamChatClient()
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
        chat_client=chat_client,
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

    def _prepare_vision(request: Any, *_a: Any, **_kw: Any) -> tuple[list[dict[str, Any]], str]:
        return ([{"role": "user", "content": "describe this", "images": ["base64-image"]}], "fake-model")

    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", _prepare_vision)
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)
    monkeypatch.setattr(
        handler,
        "get_cached_ollama_capabilities",
        lambda *_a, **_kw: frozenset({"completion", "tools", "vision"}),
    )

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "stream": True,
            "messages": [{"role": "user", "content": "describe this"}],
            "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    assert "vision ok" in r.get_data(as_text=True)

    assert chat_client.payloads
    sent = chat_client.payloads[0]
    assert sent.get("tools")
    assert sent["messages"][0]["images"] == ["base64-image"]
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    request_trace = trace.get("request") or {}
    response_trace = trace.get("response") or {}
    assert request_trace.get("native_tools_preserved_for_vision") is True
    assert request_trace.get("native_tools_suppressed_for_vision") is not True
    assert request_trace.get("tools_count_effective") == 1
    assert response_trace.get("native_tools") is True


def test_streaming_vision_request_preserves_native_tools_even_when_caps_omit_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_proxy.chat_completions_handler as handler

    import api.http.rag_routes as rag_routes

    class VisionStreamChatClient:
        def __init__(self) -> None:
            self._url = "http://fake-ollama/api/chat"
            self.payloads: list[dict[str, Any]] = []

        def iter_chat_api_stream_events(self, payload: dict[str, Any]):
            self.payloads.append(payload)
            yield ("content_delta", "vision ok")
            yield ("done", {"done_reason": "stop", "eval_count": 6, "prompt_eval_count": 3})

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    chat_client = VisionStreamChatClient()
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
        chat_client=chat_client,
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

    def _prepare_vision(request: Any, *_a: Any, **_kw: Any) -> tuple[list[dict[str, Any]], str]:
        return ([{"role": "user", "content": "describe this", "images": ["base64-image"]}], "fake-model")

    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", _prepare_vision)
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)
    monkeypatch.setattr(
        handler,
        "get_cached_ollama_capabilities",
        lambda *_a, **_kw: frozenset({"completion", "vision"}),
    )

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "stream": True,
            "messages": [{"role": "user", "content": "describe this"}],
            "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    assert "vision ok" in r.get_data(as_text=True)

    assert chat_client.payloads
    sent = chat_client.payloads[0]
    assert sent.get("tools")
    assert sent["messages"][0]["images"] == ["base64-image"]
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    request_trace = trace.get("request") or {}
    response_trace = trace.get("response") or {}
    assert request_trace.get("native_tools_suppressed_for_vision") is not True
    assert request_trace.get("tools_count_effective") == 1
    assert response_trace.get("native_tools") is True


def test_streaming_vision_request_uses_fallback_when_model_lacks_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import llm_proxy.chat_completions_handler as handler

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Giant",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "deepseek-v4-pro:cloud",
                            "vision_model": "minimax-m3:cloud",
                            "prompt_name": "system_senior_ios_assistant_v1",
                        }
                    ]
                )
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "fallback-model"
            return _test_proxy_api_key_setting(key)

    class VisionStreamChatClient:
        def __init__(self) -> None:
            self.payloads: list[dict[str, Any]] = []

        def iter_chat_api_stream_events(self, payload: dict[str, Any]):
            self.payloads.append(payload)
            yield ("content_delta", "fallback vision ok")
            yield ("done", {"done_reason": "stop", "eval_count": 6, "prompt_eval_count": 3})

    chat_client = VisionStreamChatClient()
    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fallback-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=chat_client,
    )

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )

    def _prepare_vision(_request: Any, *_a: Any, **_kw: Any) -> tuple[list[dict[str, Any]], str]:
        return ([{"role": "user", "content": "describe this", "images": ["base64-image"]}], "deepseek-v4-pro:cloud")

    def _caps(model: str, _chat_url: str) -> frozenset[str] | None:
        if model == "deepseek-v4-pro:cloud":
            return frozenset({"completion", "tools", "thinking"})
        if model == "minimax-m3:cloud":
            return frozenset({"completion", "tools", "vision"})
        return None

    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", _prepare_vision)
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)
    monkeypatch.setattr(handler, "get_cached_ollama_capabilities", _caps)
    monkeypatch.setattr(handler, "find_cached_ollama_vision_model", lambda *_a, **_kw: "minimax-m3:cloud")

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "Giant",
            "stream": True,
            "messages": [{"role": "user", "content": "describe this"}],
            "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )
    assert r.status_code == 200
    assert "fallback vision ok" in r.get_data(as_text=True)

    assert chat_client.payloads
    sent = chat_client.payloads[0]
    assert sent["model"] == "minimax-m3:cloud"
    assert sent.get("tools")
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    request_trace = trace.get("request") or {}
    assert str(request_trace.get("ollama_capabilities_lookup_url") or "").endswith("/api/chat")
    assert request_trace.get("actual_model") == "minimax-m3:cloud"
    assert request_trace.get("vision_model_fallback") == {
        "from": "deepseek-v4-pro:cloud",
        "to": "minimax-m3:cloud",
        "reason": "selected_ollama_model_lacks_vision",
    }
    assert request_trace.get("native_tools_preserved_for_vision") is True
    assert request_trace.get("tools_count_effective") == 1
    assert "vision_model_fallback" in (trace.get("warnings") or [])


def test_native_tools_finalize_nudge_stays_in_initial_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.http.rag_routes as rag_routes

    captured_payload: dict[str, Any] = {}

    class NativeStreamChatClient:
        def iter_chat_api_stream_events(self, payload: dict[str, Any]):
            captured_payload.clear()
            captured_payload.update(payload)
            yield ("content_delta", "done")
            yield ("done", {"done_reason": "stop", "eval_count": 12, "prompt_eval_count": 4})

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

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
        chat_client=NativeStreamChatClient(),
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

    def _prepare_native(request: Any, *_a: Any, **kw: Any) -> tuple[list[dict[str, Any]], str]:
        from rag_service.infrastructure.openai_ollama_tool_bridge import openai_messages_to_ollama

        if kw.get("native_tools"):
            oll = openai_messages_to_ollama([m for m in request.messages if isinstance(m, dict)])
            return [{"role": "system", "content": "system"}] + oll, "fake-model"
        return ([{"role": "user", "content": "x"}], "fake-model")

    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", _prepare_native)
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "stream": True,
            "messages": [
                {"role": "user", "content": "fix it"},
                {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": "ok"},
                {"role": "assistant", "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "read"}}]},
                {"role": "tool", "tool_call_id": "c2", "content": "ok"},
                {"role": "assistant", "tool_calls": [{"id": "c3", "type": "function", "function": {"name": "read"}}]},
                {"role": "tool", "tool_call_id": "c3", "content": "ok"},
            ],
            "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )

    assert r.status_code == 200
    _ = r.get_data(as_text=True)
    upstream_messages = captured_payload.get("messages") or []
    assert upstream_messages[0]["role"] == "system"
    assert "Prefer synthesizing the final answer now" in upstream_messages[0]["content"]
    assert [m.get("role") for m in upstream_messages].count("system") == 1
    assert upstream_messages[-1]["role"] == "tool"
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    native_diag = ((trace.get("request") or {}).get("native_tools_preflight") or {})
    assert native_diag.get("tool_loop_finalize_nudge") is True


def test_stream_trace_separates_reasoning_and_final_content_in_sse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.http.rag_routes as rag_routes
    from api.http.proxy_trace import get_response_artifacts

    class StreamingChatClient:
        def iter_chat_api_stream_events(self, _payload: dict[str, Any]):
            yield ("thinking_delta", "Plan: ")
            yield ("content_delta", "Answer")
            yield ("done", {"done_reason": "stop", "eval_count": 8, "prompt_eval_count": 4})

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

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
        chat_client=StreamingChatClient(),
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    request_id = "stream-artifacts-1"
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "stream": True,
            "client_request_id": request_id,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '"reasoning_content": "Plan: "' in body
    assert '"content": "Plan: "' not in body
    assert "Answer" in body

    cur = client.get("/api/webui/proxy-trace/current")
    assert cur.status_code == 200
    trace = (cur.get_json() or {}).get("trace") or {}
    resp = trace.get("response") or {}
    assert resp.get("has_reasoning") is True
    assert resp.get("final_content_preview") == "Answer"
    artifacts = get_response_artifacts(request_id) or {}
    assert artifacts.get("reasoning_content") == "Plan: "
    assert artifacts.get("final_content") == "Answer"
    assert artifacts.get("visible_content") == "Plan: Answer"


def test_chat_completions_non_stream_uses_ollama_provider_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llm_interactor.contracts import LLMResponse

    import api.http.rag_routes as rag_routes
    from llm_interactor import ExtensionManager

    class Runtime:
        def __init__(self) -> None:
            self.requests: list[Any] = []

        def invoke(self, request: Any) -> LLMResponse:
            self.requests.append(request)
            return LLMResponse(
                provider_id="ollama",
                model=request.model,
                text="Final answer.",
                raw={
                    "message": {
                        "role": "assistant",
                        "thinking": "Plan.",
                        "content": "Final answer.",
                    },
                    "details": {"family": "qwen"},
                    "done_reason": "stop",
                    "eval_count": 8,
                    "prompt_eval_count": 4,
                },
            )

    runtime = Runtime()

    def bootstrap_runtime(self: Any) -> None:
        self._runtime = runtime
        self._runtime_status = "ready"

    class DelegateChatClient:
        def chat_api(self, _payload: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("legacy chat_api should not be used when runtime is ready")

        def chat(self, *_a: Any, **_k: Any) -> str:
            raise AssertionError("legacy chat should not be used when runtime is ready")

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
        chat_client=DelegateChatClient(),
    )

    monkeypatch.setattr(ExtensionManager, "start_background_bootstrap", bootstrap_runtime)
    _patch_rag_answer_params(monkeypatch, fake_params, fake_deps)

    def _fake_build_extension_manager(*, deps: Any, bootstrap_extensions: bool = True) -> tuple[Any, Any, Any, Any, str]:
        del bootstrap_extensions
        from rag_service.infrastructure.provider_runtime import RuntimeResolvingChatClient

        runtime_chat = RuntimeResolvingChatClient(
            runtime=runtime,
            provider_id="ollama",
            fallback=deps.chat_client,
        )
        return None, runtime, None, runtime_chat, "ollama"

    monkeypatch.setattr("api.http.llm_proxy_wiring._build_extension_manager", _fake_build_extension_manager)
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )

    def prepare_messages(request: Any, *_a: Any, **_k: Any) -> tuple[list[dict[str, Any]], str]:
        return (
            [
                {
                    "role": "user",
                    "content": "describe this",
                    "images": ["base64-image"],
                }
            ],
            "fake-model",
        )

    monkeypatch.setattr(rag_routes, "prepare_ollama_messages", prepare_messages)
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "messages": [{"role": "user", "content": "describe this"}],
            "think": True,
        },
    )

    assert r.status_code == 200
    payload = r.get_json() or {}
    assert payload["choices"][0]["message"]["content"] == "Final answer."
    assert runtime.requests
    request = runtime.requests[0]
    assert request.provider_id == "ollama"
    assert request.operation == "chat_api"
    assert request.model == "fake-model"
    assert request.body["think"] is True
    assert request.body["messages"][0]["images"] == ["base64-image"]
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    ollama_trace = trace.get("ollama") or {}
    response_trace = trace.get("response") or {}
    token_estimates = ollama_trace.get("tokens_estimates") or {}
    assert ollama_trace.get("provider_id") == "ollama"
    assert ollama_trace.get("provider_model_id") == "fake-model"
    assert ollama_trace.get("provider_operation") == "chat_api"
    assert ollama_trace.get("provider_runtime") is True
    assert response_trace.get("latency_ms") is not None
    assert response_trace.get("ollama_eval_count") == 8
    assert response_trace.get("ollama_prompt_eval_count") == 4
    assert response_trace.get("brand_key") == "qwen"
    assert int(token_estimates.get("prompt_tokens_estimated") or 0) >= 1
    assert int(token_estimates.get("completion_tokens_estimated") or 0) >= 1


def test_chat_completions_stream_uses_ollama_provider_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llm_interactor.contracts import LLMStreamEvent

    import api.http.rag_routes as rag_routes
    from llm_interactor import ExtensionManager

    class Runtime:
        def __init__(self) -> None:
            self.requests: list[Any] = []

        def stream_invoke(self, request: Any):
            self.requests.append(request)
            yield LLMStreamEvent(
                provider_id="ollama",
                model=request.model,
                type="thinking_delta",
                data="Plan: ",
            )
            yield LLMStreamEvent(
                provider_id="ollama",
                model=request.model,
                type="content_delta",
                data="Answer",
            )
            yield LLMStreamEvent(
                provider_id="ollama",
                model=request.model,
                type="done",
                data={"done_reason": "stop", "eval_count": 9, "prompt_eval_count": 3},
            )

    runtime = Runtime()

    def bootstrap_runtime(self: Any) -> None:
        self._runtime = runtime
        self._runtime_status = "ready"

    class DelegateChatClient:
        def iter_chat_api_stream_events(self, _payload: dict[str, Any]):
            raise AssertionError("legacy stream should not be used when runtime is ready")

        def chat(self, *_a: Any, **_k: Any) -> str:
            raise AssertionError("legacy chat should not be used when runtime is ready")

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
        chat_client=DelegateChatClient(),
    )

    monkeypatch.setattr(ExtensionManager, "start_background_bootstrap", bootstrap_runtime)
    _patch_rag_answer_params(monkeypatch, fake_params, fake_deps)

    def _fake_build_extension_manager(*, deps: Any, bootstrap_extensions: bool = True) -> tuple[Any, Any, Any, Any, str]:
        del bootstrap_extensions
        from rag_service.infrastructure.provider_runtime import RuntimeResolvingChatClient

        runtime_chat = RuntimeResolvingChatClient(
            runtime=runtime,
            provider_id="ollama",
            fallback=deps.chat_client,
        )
        return None, runtime, None, runtime_chat, "ollama"

    monkeypatch.setattr("api.http.llm_proxy_wiring._build_extension_manager", _fake_build_extension_manager)
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
            "think": "medium",
        },
    )

    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '"reasoning_content": "Plan: "' in body
    assert '"content": "Answer"' in body
    assert "data: [DONE]" in body
    assert runtime.requests
    request = runtime.requests[0]
    assert request.provider_id == "ollama"
    assert request.operation == "chat_api_stream_events"
    assert request.stream is True
    assert request.body["think"] == "medium"
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    ollama_trace = trace.get("ollama") or {}
    response_trace = trace.get("response") or {}
    token_estimates = ollama_trace.get("tokens_estimates") or {}
    assert ollama_trace.get("provider_id") == "ollama"
    assert ollama_trace.get("provider_model_id") == "fake-model"
    assert ollama_trace.get("provider_operation") == "chat_api_stream_events"
    assert ollama_trace.get("provider_runtime") is True
    assert response_trace.get("latency_ms") is not None
    assert response_trace.get("final_content_preview") == "Answer"
    assert response_trace.get("reasoning_preview") == "Plan: "
    assert response_trace.get("ollama_eval_count") == 9
    assert response_trace.get("ollama_prompt_eval_count") == 3
    assert int(token_estimates.get("prompt_tokens_estimated") or 0) >= 1
    assert int(token_estimates.get("completion_tokens_estimated") or 0) >= 1


def test_stream_reasoning_only_guard_stops_visible_repeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.http.rag_routes as rag_routes

    monkeypatch.setenv("LLM_PROXY_REASONING_ONLY_GUARD_CHARS", "512")

    class StreamingChatClient:
        def iter_chat_api_stream_events(self, _payload: dict[str, Any]):
            yield ("thinking_delta", "x" * 300)
            yield ("thinking_delta", "y" * 300)
            yield ("thinking_delta", "z" * 300)
            yield ("done", {"done_reason": "stop", "eval_count": 900, "prompt_eval_count": 4})

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

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
        chat_client=StreamingChatClient(),
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "reasoning_content" in body
    assert "reasoning-only response guard triggered" in body
    assert '"content": "' + ("x" * 20) not in body
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    assert "reasoning_only_guard_triggered" in (trace.get("warnings") or [])
    assert (trace.get("response") or {}).get("reasoning_only_guard_triggered") is True


def test_non_stream_logs_store_only_previews_for_reasoning_and_final_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.http.rag_routes as rag_routes

    captured_log: dict[str, Any] = {}

    class NonStreamingChatClient:
        def chat_api(self, _payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "message": {
                    "role": "assistant",
                    "thinking": "Internal reasoning that should stay preview-only.",
                    "content": "Final answer.",
                },
                "done_reason": "stop",
            }

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    class FakeSessionManager:
        def get_or_create_session(self, _session_id: str) -> None:
            return None

    class FakeLogsRepo:
        def add_log(self, **kwargs: Any) -> int:
            captured_log.clear()
            captured_log.update(kwargs)
            return 1

        def upsert_proxy_journal_log(
            self,
            *,
            message: str,
            metadata: dict[str, Any],
            trace_chain_id: str = "",
        ) -> int:
            captured_log.clear()
            captured_log["message"] = message
            captured_log["metadata"] = metadata
            if trace_chain_id:
                captured_log["trace_chain_id"] = trace_chain_id
            return 1

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fake-model",
        log_preview_chars=80,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=NonStreamingChatClient(),
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)
    monkeypatch.setattr(rag_routes, "get_session_manager", lambda: FakeSessionManager())
    monkeypatch.setattr(rag_routes, "get_logs_repository", lambda: FakeLogsRepo())

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    data = r.get_json() or {}
    content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
    msg = ((data.get("choices") or [{}])[0]).get("message") or {}
    assert content == "Final answer."
    assert msg.get("reasoning_content") == "Internal reasoning that should stay preview-only."

    metadata = captured_log.get("metadata") or {}
    trace = metadata.get("trace") or {}
    response = trace.get("response") or {}
    assert response.get("has_reasoning") is True
    assert response.get("reasoning_preview") == "Internal reasoning that should stay preview-only."
    assert response.get("final_content_preview") == "Final answer."
    assert "reasoning_content" not in response
    assert "final_content" not in response


def _build_rag_route_test_chat_client() -> Any:
    class ChatClient:
        def chat_api(self, _payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "message": {"role": "assistant", "content": "ok"},
                "done_reason": "stop",
            }

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    return ChatClient()


def _build_rag_route_fake_params(model_name: str = "fake-model") -> SimpleNamespace:
    return SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name=model_name,
        log_preview_chars=200,
    )


def test_build_rag_collection_uses_build_specific_qdrant_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    seen: dict[str, Any] = {}

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Docs-worker",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "fake-model",
                            "prompt_name": "system_senior_ios_assistant_v1",
                            "rag_collection": "build-docs",
                        }
                    ]
                )
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "fallback-model"
            if key == "rag_collection":
                return ""
            return _test_proxy_api_key_setting(key)

    chat_client = _build_rag_route_test_chat_client()
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=chat_client,
    )

    def fake_get_rag_answer_params(*, webui_dir=None, collection_name=None, **_kwargs):
        seen["collection_name"] = collection_name
        return _build_rag_route_fake_params(), fake_deps

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", fake_get_rag_answer_params)
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "Docs-worker",
            "messages": [{"role": "user", "content": "How do I use SwiftUI navigation?"}],
        },
    )
    assert r.status_code == 200
    assert seen.get("collection_name") == "build-docs"
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    assert trace.get("request", {}).get("collection_source") == "proxy_settings.rag_collection"


def test_build_rag_enabled_false_skips_rag_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    rag_calls = {"count": 0}

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "No-rag-worker",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "fake-model",
                            "prompt_name": "system_senior_ios_assistant_v1",
                            "rag_enabled": False,
                            "rag_collection": "ignored-docs",
                        }
                    ]
                )
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "fallback-model"
            return _test_proxy_api_key_setting(key)

    chat_client = _build_rag_route_test_chat_client()
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=chat_client,
    )

    def fake_build_rag_context(*_args, **_kwargs):
        rag_calls["count"] += 1
        return (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        )

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (_build_rag_route_fake_params(), fake_deps))
    monkeypatch.setattr(rag_routes, "build_rag_context", fake_build_rag_context)
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "No-rag-worker",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert r.status_code == 200
    assert rag_calls["count"] == 0
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    assert trace.get("request", {}).get("skip_rag_retrieval") is True


def test_build_without_rag_collection_falls_back_to_app_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    seen: dict[str, Any] = {}

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Default-worker",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "fake-model",
                            "prompt_name": "system_senior_ios_assistant_v1",
                        }
                    ]
                )
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "fallback-model"
            if key == "rag_collection":
                return "global-docs"
            return _test_proxy_api_key_setting(key)

    chat_client = _build_rag_route_test_chat_client()
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=chat_client,
    )

    def fake_get_rag_answer_params(*, webui_dir=None, collection_name=None, **_kwargs):
        seen["collection_name"] = collection_name
        return _build_rag_route_fake_params(), fake_deps

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", fake_get_rag_answer_params)
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "Default-worker",
            "messages": [{"role": "user", "content": "Explain Combine publishers"}],
        },
    )
    assert r.status_code == 200
    assert seen.get("collection_name") == "global-docs"
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    assert trace.get("request", {}).get("collection_source") == "app_settings.rag_collection"


def test_model_build_num_predict_forwards_to_ollama_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    captured_payload: dict[str, Any] = {}

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Hard-worker",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "fake-model",
                            "prompt_name": "system_senior_ios_assistant_v1",
                            "num_predict": 65536,
                        }
                    ]
                )
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "fallback-model"
            return _test_proxy_api_key_setting(key)

    class ChatClient:
        _default_options = {"num_predict": 3072, "temperature": 0.0, "top_p": 1.0}

        def chat_api(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured_payload.clear()
            captured_payload.update(payload)
            return {
                "message": {"role": "assistant", "content": "ok"},
                "done_reason": "stop",
                "eval_count": 12,
                "prompt_eval_count": 4,
            }

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fallback-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=ChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    r = app.test_client().post(
        "/v1/chat/completions",
        json={"model": "Hard-worker", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert r.status_code == 200
    assert captured_payload.get("options", {}).get("num_predict") == 65536
    assert captured_payload.get("think") is False

    trace = (app.test_client().get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    assert (trace.get("request") or {}).get("effective_num_predict") == 65536
    assert (trace.get("request") or {}).get("ollama_think") is False


def test_request_max_tokens_overrides_build_num_predict_and_warns_when_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    captured_payload: dict[str, Any] = {}

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Hard-worker",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "fake-model",
                            "prompt_name": "system_senior_ios_assistant_v1",
                            "num_predict": 65536,
                        }
                    ]
                )
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "fallback-model"
            return _test_proxy_api_key_setting(key)

    class ChatClient:
        _default_options = {"num_predict": 3072, "temperature": 0.0, "top_p": 1.0}

        def chat_api(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured_payload.clear()
            captured_payload.update(payload)
            return {
                "message": {"role": "assistant", "thinking": "plan only", "content": ""},
                "done_reason": "stop",
                "eval_count": 64,
                "prompt_eval_count": 4,
            }

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fallback-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=ChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "Hard-worker",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )

    assert r.status_code == 200
    payload = r.get_json() or {}
    choice = (payload.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "")
    assert "output token budget exhausted" not in content
    assert choice.get("finish_reason") == "length"
    assert captured_payload.get("options", {}).get("num_predict") == 64

    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    assert (trace.get("request") or {}).get("effective_num_predict") == 64
    assert "output_token_budget_exhausted" in (trace.get("warnings") or [])


def test_request_max_tokens_cannot_exceed_build_num_predict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    captured_payload: dict[str, Any] = {}

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Capped-worker",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "fake-model",
                            "prompt_name": "system_senior_ios_assistant_v1",
                            "num_predict": 1024,
                        }
                    ]
                )
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "fallback-model"
            return _test_proxy_api_key_setting(key)

    class ChatClient:
        _default_options = {"num_predict": 3072, "temperature": 0.0, "top_p": 1.0}

        def chat_api(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured_payload.clear()
            captured_payload.update(payload)
            return {
                "message": {"role": "assistant", "content": "ok"},
                "done_reason": "stop",
                "eval_count": 12,
                "prompt_eval_count": 4,
            }

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fallback-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=ChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "Capped-worker",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert r.status_code == 200
    assert captured_payload.get("options", {}).get("num_predict") == 1024
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    assert (trace.get("request") or {}).get("effective_num_predict") == 1024


def test_model_build_num_predict_reserves_input_budget_for_upstream_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    captured_payload: dict[str, Any] = {}

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Budget-worker",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "fake-model",
                            "prompt_name": "system_senior_ios_assistant_v1",
                            "num_ctx": 8192,
                            "num_predict": 1024,
                        }
                    ]
                )
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "fallback-model"
            return _test_proxy_api_key_setting(key)

    class ChatClient:
        _default_options = {"num_predict": 3072, "temperature": 0.0, "top_p": 1.0}

        def chat_api(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured_payload.clear()
            captured_payload.update(payload)
            return {
                "message": {"role": "assistant", "content": "ok"},
                "done_reason": "stop",
                "eval_count": 12,
                "prompt_eval_count": 4,
            }

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fallback-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=ChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
    monkeypatch.setattr(rag_routes, "get_rag_answer_params", lambda **kwargs: (fake_params, fake_deps))
    monkeypatch.setattr(
        rag_routes,
        "build_rag_context",
        lambda *args, **kwargs: (
            SimpleNamespace(context_text="", chunks_info=[], max_score=0.0),
            {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0},
        ),
    )
    huge_history = "old assistant chatter " * 4000
    monkeypatch.setattr(
        rag_routes,
        "prepare_ollama_messages",
        lambda request, *_a, **_k: (
            [
                {"role": "system", "content": "system"},
                {"role": "assistant", "content": huge_history},
                {"role": "user", "content": request.messages[-1]["content"]},
            ],
            "fake-model",
        ),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={"model": "Budget-worker", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert r.status_code == 200
    assert captured_payload.get("options", {}).get("num_predict") == 1024
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    budget = ((trace.get("request") or {}).get("input_budget") or {})
    assert budget.get("reserved_output_tokens") == 1024
    assert len(json.dumps(captured_payload.get("messages") or [], ensure_ascii=False)) <= int(
        budget.get("input_budget_json_chars")
    )
    compact = (trace.get("request") or {}).get("upstream_context_compaction") or {}
    assert compact.get("compacted") is True


def test_request_max_tokens_overrides_input_budget_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    captured_payload: dict[str, Any] = {}

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Budget-worker",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "fake-model",
                            "prompt_name": "system_senior_ios_assistant_v1",
                            "num_ctx": 8192,
                            "num_predict": 4096,
                        }
                    ]
                )
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "fallback-model"
            return _test_proxy_api_key_setting(key)

    class ChatClient:
        _default_options = {"num_predict": 3072, "temperature": 0.0, "top_p": 1.0}

        def chat_api(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured_payload.clear()
            captured_payload.update(payload)
            return {
                "message": {"role": "assistant", "content": "ok"},
                "done_reason": "stop",
                "eval_count": 12,
                "prompt_eval_count": 4,
            }

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fallback-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=ChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
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
        lambda request, *_a, **_k: (
            [
                {"role": "system", "content": "system"},
                {"role": "assistant", "content": "old assistant chatter " * 1000},
                {"role": "user", "content": request.messages[-1]["content"]},
            ],
            "fake-model",
        ),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "Budget-worker",
            "max_tokens": 512,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert r.status_code == 200
    assert captured_payload.get("options", {}).get("num_predict") == 512
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    budget = ((trace.get("request") or {}).get("input_budget") or {})
    assert budget.get("reserved_output_tokens") == 512
    assert (trace.get("request") or {}).get("effective_num_predict") == 512


def test_model_build_max_agent_steps_suppresses_tools_at_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import api.http.rag_routes as rag_routes
    from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY

    captured_payload: dict[str, Any] = {}
    chat_calls = {"count": 0}

    class Repo:
        def get_app_setting(self, key: str):
            if key == LLM_PROXY_BUILDS_APP_KEY:
                return json.dumps(
                    [
                        {
                            "id": "Step-worker",
                            "backend": "dumb",
                            "provider_id": "ollama",
                            "model": "fake-model",
                            "prompt_name": "system_senior_ios_assistant_v1",
                            "max_agent_steps": 2,
                        }
                    ]
                )
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "fallback-model"
            return _test_proxy_api_key_setting(key)

    class ChatClient:
        _default_options = {"num_predict": 3072, "temperature": 0.0, "top_p": 1.0}

        def chat_api(self, payload: dict[str, Any]) -> dict[str, Any]:
            chat_calls["count"] += 1
            captured_payload.clear()
            captured_payload.update(payload)
            return {
                "message": {"role": "assistant", "content": "final"},
                "done_reason": "stop",
                "eval_count": 12,
                "prompt_eval_count": 4,
            }

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="fallback-model",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=ChatClient(),
    )

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())
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
        lambda request, *_a, **_k: ([{"role": "user", "content": "finalize"}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "Step-worker",
            "messages": [
                {"role": "user", "content": "fix it"},
                {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "grep"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": "ok"},
                {"role": "assistant", "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "grep"}}]},
                {"role": "tool", "tool_call_id": "c2", "content": "ok"},
            ],
            "tools": [{"type": "function", "function": {"name": "grep", "parameters": {"type": "object"}}}],
            "tool_choice": "auto",
        },
    )

    assert r.status_code == 200
    assert chat_calls["count"] == 0
    assert "tools" not in captured_payload
    assert "tool_choice" not in captured_payload
    payload = r.get_json() or {}
    message = ((payload.get("choices") or [{}])[0]).get("message") or {}
    assert not message.get("tool_calls")
    assert "max_agent_steps limit reached after 2 tool rounds (grep)" in str(message.get("content") or "")
    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    req = trace.get("request") or {}
    assert req.get("effective_max_agent_steps") == 2
    assert req.get("tool_loop_limit_reached") is True
    assert req.get("tools_suppressed_for_step_limit") is True
    assert "tool_loop_limit_reached" in (trace.get("warnings") or [])
    assert "tool_loop_limit_response_forced" in (trace.get("warnings") or [])


def test_streaming_budget_exhaustion_is_visible_to_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.http.rag_routes as rag_routes

    class StreamingChatClient:
        _default_options = {"num_predict": 3072, "temperature": 0.0, "top_p": 1.0}

        def iter_chat_api_stream_events(self, _payload: dict[str, Any]):
            yield ("content_delta", "partial")
            yield ("done", {"done_reason": "stop", "eval_count": 8, "prompt_eval_count": 4})

        def chat(self, *_a: Any, **_k: Any) -> str:
            return ""

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
        chat_client=StreamingChatClient(),
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
        lambda request, *_a, **_k: ([{"role": "user", "content": request.messages[-1]["content"]}], "fake-model"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-proxy-ollama-model",
            "stream": True,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "partial" in body
    assert "output token budget exhausted" not in body
    assert '"finish_reason": "length"' in body

    trace = (client.get("/api/webui/proxy-trace/current").get_json() or {}).get("trace") or {}
    assert "output_token_budget_exhausted" in (trace.get("warnings") or [])


def test_shell_tool_call_sanitizer_adds_erroraction_for_recursive_get_childitem() -> None:
    import json

    import llm_proxy.chat_completions as cc

    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "shell",
                "arguments": json.dumps({"command": 'powershell.exe -Command "Get-ChildItem -Recurse -Depth 2"'}),
            },
        }
    ]
    out, fixed = cc._sanitize_outgoing_shell_tool_calls(tool_calls)
    assert fixed == 1
    args = json.loads(out[0]["function"]["arguments"])
    assert "-ErrorAction SilentlyContinue" in args["command"]


def test_shell_tool_call_sanitizer_keeps_command_with_explicit_erroraction() -> None:
    import json

    import llm_proxy.chat_completions as cc

    cmd = 'powershell.exe -Command "Get-ChildItem -Recurse -Depth 2 -ErrorAction Stop"'
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "shell", "arguments": json.dumps({"command": cmd})},
        }
    ]
    out, fixed = cc._sanitize_outgoing_shell_tool_calls(tool_calls)
    assert fixed == 0
    args = json.loads(out[0]["function"]["arguments"])
    assert args["command"] == cmd


def test_tool_round_stats_since_last_user_counts_shell_rounds() -> None:
    import llm_proxy.chat_completions as cc

    messages = [
        {"role": "user", "content": "Explain this codebase"},
        {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "shell"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"role": "assistant", "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "shell"}}]},
        {"role": "tool", "tool_call_id": "c2", "content": "ok"},
    ]
    stats = cc._tool_round_stats_since_last_user(messages)
    assert stats["rounds"] == 2
    assert stats["shell_rounds"] == 2
    assert stats["non_shell_rounds"] == 0
    assert stats["single_tool_rounds"] == 2
    assert stats["dominant_tool"] == "shell"
    assert stats["dominant_tool_rounds"] == 2


def test_tool_round_stats_since_last_user_tracks_dominant_tool() -> None:
    import llm_proxy.chat_completions as cc

    messages = [
        {"role": "user", "content": "Investigate issue"},
        {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "shell"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"role": "assistant", "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "shell"}}]},
        {"role": "tool", "tool_call_id": "c2", "content": "ok"},
        {"role": "assistant", "tool_calls": [{"id": "c3", "type": "function", "function": {"name": "web_search"}}]},
        {"role": "tool", "tool_call_id": "c3", "content": "ok"},
    ]
    stats = cc._tool_round_stats_since_last_user(messages)
    assert stats["rounds"] == 3
    assert stats["single_tool_rounds"] == 3
    assert stats["dominant_tool"] == "shell"
    assert stats["dominant_tool_rounds"] == 2
