from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_ERROR_MANAGER = _ROOT / "CoreModules" / "ErrorManager"
if str(_ERROR_MANAGER) not in sys.path:
    sys.path.insert(0, str(_ERROR_MANAGER))

from llm_interactor.contracts import LLMResponse
from rag_service.domain.errors import EmbeddingError
from rag_service.infrastructure.provider_runtime import RuntimeBackedEmbeddingProvider, RuntimeBackedRerankClient


class _Runtime:
    def __init__(self) -> None:
        self.requests = []

    def invoke(self, request):
        self.requests.append(request)
        if request.operation == "embed":
            if request.input_texts is not None:
                return LLMResponse(
                    provider_id="ollama",
                    model=request.model,
                    raw={"embeddings": [[1.0, 2.0], [3.0, 4.0]]},
                )
            return LLMResponse(
                provider_id="ollama",
                model=request.model,
                raw={"embedding": [0.5, 1.5]},
            )
        if request.operation == "rerank":
            return LLMResponse(
                provider_id="ollama",
                model=request.model,
                text="[2, 1]",
                raw={"response": "[2, 1]"},
            )
        raise AssertionError(request.operation)


def test_runtime_backed_embedding_provider_invokes_runtime_for_single_and_batch() -> None:
    runtime = _Runtime()
    provider = RuntimeBackedEmbeddingProvider(runtime=runtime, model="embed-model")

    assert provider.embed("one") == [0.5, 1.5]
    assert provider.embed_batch(["one", "two"]) == [[1.0, 2.0], [3.0, 4.0]]

    assert [request.operation for request in runtime.requests] == ["embed", "embed"]
    assert runtime.requests[0].input_text == "one"
    assert runtime.requests[1].input_texts == ["one", "two"]


def test_runtime_backed_embedding_provider_preserves_batch_count_errors() -> None:
    class BadRuntime:
        def invoke(self, request):
            return LLMResponse(provider_id="ollama", model=request.model, raw={"embeddings": [[1.0]]})

    provider = RuntimeBackedEmbeddingProvider(runtime=BadRuntime(), model="embed-model")

    with pytest.raises(EmbeddingError, match="1 embeddings for 2 inputs"):
        provider.embed_batch(["one", "two"])


def test_runtime_backed_rerank_client_skips_when_runtime_unavailable() -> None:
    runtime = _Runtime()
    client = RuntimeBackedRerankClient(runtime=runtime, model="rerank-model")

    assert client.rerank("question", "prompt") == "[2, 1]"
    request = runtime.requests[0]
    assert request.operation == "rerank"
    assert request.rerank_query == "question"
    assert request.rerank_prompt == "prompt"

    unavailable = RuntimeBackedRerankClient(runtime_getter=lambda: None, model="rerank-model")
    assert unavailable.rerank("q", "p") is None


def test_rag_container_can_supply_provider_backed_clients() -> None:
    from rag_service.infrastructure import container
    from rag_service.infrastructure.provider_runtime import RuntimeResolvingChatClient

    runtime = _Runtime()

    embed = container.default_embed_provider(runtime=runtime, model="embed-model")
    rerank = container.default_rerank_client(runtime=runtime, model="rerank-model")
    chat = container.default_chat_client(runtime=runtime, model="chat-model")

    assert isinstance(embed, RuntimeBackedEmbeddingProvider)
    assert isinstance(rerank, RuntimeBackedRerankClient)
    assert isinstance(chat, RuntimeResolvingChatClient)
