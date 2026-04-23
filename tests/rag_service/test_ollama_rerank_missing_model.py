from __future__ import annotations

from rag_service.infrastructure.cli_runner import OllamaInteractorCliError
from rag_service.infrastructure import ollama_rerank


def test_rerank_missing_model_is_disabled_after_first_failure(monkeypatch) -> None:
    calls = {"generate": 0}
    model = "missing-reranker:latest"

    ollama_rerank._disabled_missing_models.clear()

    def fake_invoke_rerank(*_args, **_kwargs):
        raise OllamaInteractorCliError("404 Client Error: Not Found for url: /api/rerank")

    def fake_invoke_generate(*_args, **_kwargs):
        calls["generate"] += 1
        raise OllamaInteractorCliError(f"404 Client Error: model '{model}' not found")

    monkeypatch.setattr(ollama_rerank, "invoke_rerank", fake_invoke_rerank)
    monkeypatch.setattr(ollama_rerank, "invoke_generate", fake_invoke_generate)

    client = ollama_rerank.OllamaRerankClient(base_url="http://localhost:11434/api/generate", model=model)
    prompt = "Excerpt 1:\nA\n\nExcerpt 2:\nB"

    assert client.rerank("Q", prompt) is None
    assert client.rerank("Q", prompt) is None
    assert calls["generate"] == 1

    ollama_rerank._disabled_missing_models.clear()
