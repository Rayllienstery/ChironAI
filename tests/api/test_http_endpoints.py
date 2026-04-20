"""
Light integration tests for HTTP endpoints (Flask test client).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


class _OllamaShimChatClient:
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


def test_proxy_logs_passes_autocomplete_only_to_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/webui/proxy-logs?autocomplete_only=1 filters autocomplete rows in the repository."""
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

    import api.http.webui_routes as wr

    last_kwargs: dict = {}

    class FakeRepo:
        def get_logs(self, **kwargs):
            last_kwargs.clear()
            last_kwargs.update(kwargs)
            return []

    monkeypatch.setattr(wr, "get_logs_repository", lambda: FakeRepo())

    from api.http.rag_routes import create_app

    app = create_app()
    client = app.test_client()
    r = client.get("/api/webui/proxy-logs?autocomplete_only=1&limit=5")
    assert r.status_code == 200
    assert last_kwargs.get("autocomplete_only") is True
    assert last_kwargs.get("session_id") == "proxy"


def test_proxy_logs_default_no_autocomplete_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

    import api.http.webui_routes as wr

    last_kwargs: dict = {}

    class FakeRepo:
        def get_logs(self, **kwargs):
            last_kwargs.clear()
            last_kwargs.update(kwargs)
            return []

    monkeypatch.setattr(wr, "get_logs_repository", lambda: FakeRepo())

    from api.http.rag_routes import create_app

    app = create_app()
    client = app.test_client()
    r = client.get("/api/webui/proxy-logs?limit=5")
    assert r.status_code == 200
    assert last_kwargs.get("autocomplete_only") is None


def test_health_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys
    from unittest.mock import MagicMock

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

    ok = MagicMock()
    ok.ok = True

    def fake_get(url: str, timeout: float = 0) -> MagicMock:
        return ok

    monkeypatch.setattr("infrastructure.stack_health.requests.get", fake_get)

    from api.http.rag_routes import create_app

    app = create_app()
    client = app.test_client()
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json() or {}
    assert data.get("status") == "healthy"
    assert data.get("service") == "rag_proxy"
    comps = data.get("components") or {}
    assert comps.get("ollama") == "healthy"
    assert comps.get("qdrant") == "healthy"
    assert data.get("timestamp")


def test_health_endpoint_503_when_qdrant_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys
    from unittest.mock import MagicMock

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

    ollama_ok = MagicMock()
    ollama_ok.ok = True
    qdrant_bad = MagicMock()
    qdrant_bad.ok = False

    def fake_get(url: str, timeout: float = 0) -> MagicMock:
        if "qdrant" in url or "/collections" in url:
            return qdrant_bad
        return ollama_ok

    monkeypatch.setattr("infrastructure.stack_health.requests.get", fake_get)

    from api.http.rag_routes import create_app

    app = create_app()
    r = app.test_client().get("/health")
    assert r.status_code == 503
    data = r.get_json() or {}
    assert data.get("status") == "unhealthy"
    assert (data.get("components") or {}).get("qdrant") == "unhealthy"


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

    app = create_app()
    client = app.test_client()
    r = client.get("/v1/models")
    assert r.status_code == 200
    data = r.get_json() or {}
    ids = [m.get("id") for m in data.get("data") or []]
    assert "ChironAI-Autocomplete" in ids


def test_chat_completions_chironai_autocomplete_uses_same_prompt_template_as_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logical id ChironAI-Autocomplete uses the same prompt template as Worker and maps to the AC Ollama tag."""
    import json
    from types import SimpleNamespace

    import api.http.rag_routes as rag_routes

    monkeypatch.setenv("LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL", "fast-ac-model")

    class Repo:
        def get_app_setting(self, key: str):
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return ""
            return None

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
    ollama_captured: dict = {}

    def _fake_ollama_generate_post(url, json=None, timeout=None, stream=False, **kwargs):  # noqa
        ollama_captured["url"] = url
        ollama_captured["body"] = json

        class _Resp:
            def raise_for_status(self) -> None:
                pass

            def json(self):
                return {
                    "response": "generated",
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 3,
                    "eval_count": 2,
                }

            def close(self) -> None:
                pass

        return _Resp()

    monkeypatch.setattr("llm_proxy.completions_generate.requests.post", _fake_ollama_generate_post)
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
    assert r_legacy.status_code == 200
    leg = r_legacy.get_json() or {}
    assert leg.get("object") == "text_completion"
    assert leg.get("model") == "ChironAI-Autocomplete"
    leg_choices = leg.get("choices") or []
    assert len(leg_choices) >= 1
    assert leg_choices[0].get("text") == "generated"
    assert str(ollama_captured.get("url", "")).endswith("/api/generate")
    lego = ollama_captured.get("body") or {}
    assert lego.get("model") == "fast-ac-model"
    assert lego.get("prompt") == "def foo():"

    r_zed = client.post(
        "/v1/completions",
        json={"model": "ChironAI-Autocomplete", "prompt": "def foo():", "max_tokens": 64},
    )
    assert r_zed.status_code == 200
    zj = r_zed.get_json() or {}
    assert zj.get("object") == "text_completion"
    zchoices = zj.get("choices") or []
    assert len(zchoices) >= 1
    assert "text" in zchoices[0]
    assert zchoices[0].get("index") == 0
    assert zchoices[0].get("text") == "generated"
    assert zj.get("model") == "ChironAI-Autocomplete"
    assert str(ollama_captured.get("url", "")).endswith("/api/generate")
    ob = ollama_captured.get("body") or {}
    assert ob.get("model") == "fast-ac-model"
    assert ob.get("prompt") == "def foo():"
    assert ob.get("raw") is True
    assert ob.get("options", {}).get("num_predict") == 64


def test_v1_completions_forwards_suffix_to_ollama_generate(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI ``suffix`` is passed as native Ollama ``suffix`` (FIM), not merged into prompt."""
    import json
    from types import SimpleNamespace

    import api.http.rag_routes as rag_routes

    monkeypatch.setenv("LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL", "fast-ac-model")

    class Repo:
        def get_app_setting(self, key: str):
            if key == "proxy_settings":
                return json.dumps({"prompt_name": "system_senior_ios_assistant_v1"})
            if key == "proxy_model":
                return "worker-ollama"
            return None

    monkeypatch.setattr(rag_routes, "get_settings_repository", lambda: Repo())

    class FakeChatClient:
        def chat(self, *_a, **_k):
            return "x"

        def stream_chat(self, *_a, **_k):
            yield ""

    fc = FakeChatClient()
    fc._url = "http://ollama.test:11434/api/chat"
    fake_params = SimpleNamespace(
        system_prefix="",
        system_suffix="",
        context_chunk_chars=500,
        context_total_chars=2000,
        confidence_threshold=0.0,
        model_name="worker-ollama",
        log_preview_chars=200,
    )
    fake_deps = SimpleNamespace(
        rag_repo=object(),
        embed_provider=object(),
        rerank_client=None,
        chat_client=_OllamaShimChatClient(fc),
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
        lambda *args, **kwargs: ([{"role": "user", "content": "u"}], "worker-ollama"),
    )
    monkeypatch.setattr(rag_routes, "get_proxy_rerank_enabled", lambda: False)

    ollama_captured: dict = {}

    def _fake_post(url, json=None, timeout=None, stream=False, **kwargs):  # noqa
        ollama_captured["body"] = json

        class _Resp:
            def raise_for_status(self) -> None:
                pass

            def json(self):
                return {"response": "mid", "done": True, "done_reason": "stop"}

            def close(self) -> None:
                pass

        return _Resp()

    monkeypatch.setattr("llm_proxy.completions_generate.requests.post", _fake_post)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/v1/completions",
        json={
            "model": "ChironAI-Autocomplete",
            "prompt": "<|fim_prefix|>a",
            "suffix": "<|fim_suffix|>b<|fim_middle|>",
            "max_tokens": 32,
        },
    )
    assert r.status_code == 200
    ob = ollama_captured.get("body") or {}
    assert ob.get("prompt") == "<|fim_prefix|>a"
    assert ob.get("suffix") == "<|fim_suffix|>b<|fim_middle|>"
    assert ob.get("options", {}).get("num_predict") == 32


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
                return None

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
            from infrastructure.ollama.openai_ollama_tool_bridge import openai_messages_to_ollama

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
            "content": "Напиши Hello World на Swift 5 [@test.swift](file:///C:/Users/Raylee/Desktop/test.swift)",
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
                    "content": "Напиши Hello World на Swift 5 [@test.swift](file:///C:/Users/Raylee/Desktop/test.swift)",
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
        def chat(self, _messages, _model, stream=False, options=None):  # noqa
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
            return '{"file_path":"C:/Users/Raylee/AI/test.swift","mode":"edit","new_text":"noop\\n"}'

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
                return {"message": {"role": "assistant", "content": "Файл уже обновлён."}}
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
        from infrastructure.ollama.openai_ollama_tool_bridge import openai_messages_to_ollama

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
    assert "обновл" in content.lower() or "already" in content.lower()


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
            return None

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
    import api.http.rag_routes as rag_routes
    import llm_proxy.v1_blueprint as v1_blueprint

    logged: list[tuple[str, str, str | None]] = []

    def fake_log_webui_error(source: str, error: Exception, extra: dict[str, Any]) -> None:
        logged.append((source, type(error).__name__, (extra or {}).get("stage")))

    monkeypatch.setattr(rag_routes, "log_webui_error", fake_log_webui_error)

    def raising_chat_completions(_wiring):
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
    import api.http.rag_routes as rag_routes
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify, request

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
    import api.http.rag_routes as rag_routes
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify

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
            {"type": "unknown_codex_tool_xyz"},
        ]
    )
    assert tools == []
    assert diag.get("tools_count_raw") == 3
    assert diag.get("tools_count_normalized") == 0
    dropped = set(diag.get("tools_types_dropped") or [])
    assert {"mcp_server", "image_generation", "unknown_codex_tool_xyz"}.issubset(dropped)


def test_v1_responses_tools_normalizer_maps_codex_builtin_tools_to_functions() -> None:
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


def test_v1_responses_tools_normalizer_accepts_codex_flat_function_tools() -> None:
    """Codex often sends ``type:function`` with ``name``/``parameters`` at top level (no ``function`` dict)."""
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
                "content": [{"type": "output_text", "text": "Hello codex", "annotations": []}],
            }
        ],
        "output_text": "Hello codex",
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
                assert "Hello codex" in json.dumps(item)
                return
    raise AssertionError("message output_item.done with content not found")


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
    import api.http.rag_routes as rag_routes
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify

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
    import api.http.rag_routes as rag_routes
    import llm_proxy.v1_blueprint as v1_blueprint
    from flask import jsonify

    v1_blueprint._RESPONSES_HISTORY.clear()
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
