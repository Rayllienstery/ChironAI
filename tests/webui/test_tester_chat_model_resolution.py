"""Model Tester uses saved proxy_model when request sends logical RAG id (same as /api/webui/chat)."""

from __future__ import annotations

from types import SimpleNamespace


def test_tester_chat_resolves_logical_model_via_proxy_model_setting(monkeypatch) -> None:
    import api.http.rag_routes as rag_routes
    from api.http import webui_routes as wr

    captured: dict[str, str | None] = {}

    class CaptureChat:
        def chat(self, _messages, model, stream=False, options=None):
            captured["model"] = model
            return "pong"

        def stream_chat(self, *_a, **_k):
            yield ""

    class FakeSettings:
        def get_app_setting(self, key: str):
            if key == "proxy_model":
                return "resolved-from-webui-settings"
            if key == "rag_collection":
                return ""
            return None

        def get_tester_settings(self, _session_id: str):
            return None

    def fake_get_rag_answer_params(**_kwargs):
        return (
            SimpleNamespace(
                system_prefix="",
                system_suffix="",
                context_chunk_chars=100,
                context_total_chars=1000,
                confidence_threshold=0.0,
                model_name="from-env-config-model",
                log_preview_chars=200,
            ),
            SimpleNamespace(
                rag_repo=object(),
                embed_provider=object(),
                rerank_client=None,
                chat_client=CaptureChat(),
            ),
        )

    monkeypatch.setattr(wr, "get_settings_repository", lambda: FakeSettings())
    monkeypatch.setattr(wr, "get_rag_answer_params", fake_get_rag_answer_params)

    app = rag_routes.create_app()
    client = app.test_client()
    r = client.post(
        "/api/webui/tester/chat",
        json={
            "session_id": "test-session",
            "messages": [{"role": "user", "content": "hi"}],
            "use_rag": False,
            "model": "ChironAI-Worker",
        },
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    assert captured.get("model") == "resolved-from-webui-settings"
    body = r.get_json() or {}
    assert body.get("model") == "resolved-from-webui-settings"
