from __future__ import annotations

from llm_proxy.chat_completions import _apply_selected_rerank_model


class _RerankClient:
    def __init__(self) -> None:
        self._model = "old-rerank"


def test_apply_selected_rerank_model_uses_proxy_setting() -> None:
    client = _RerankClient()
    trace = {"request": {}}

    out = _apply_selected_rerank_model(
        client,
        {"rerank_model": "bbjson/bge-reranker-base:latest"},
        trace,
    )

    assert out is client
    assert client._model == "bbjson/bge-reranker-base:latest"
    assert trace["request"]["rerank_model"] == "bbjson/bge-reranker-base:latest"
    assert trace["request"]["rerank_model_source"] == "proxy_settings.rerank_model"
    assert trace["request"]["rerank_model_override"] == "bbjson/bge-reranker-base:latest"


def test_apply_selected_rerank_model_ignores_empty_proxy_setting() -> None:
    client = _RerankClient()
    trace = {"request": {}}

    _apply_selected_rerank_model(client, {"rerank_model": ""}, trace)

    assert client._model == "old-rerank"
    assert trace["request"] == {}
