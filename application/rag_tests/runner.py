"""
Synchronous RAG test runner for CLI (no Flask/HTTP).

Uses the same RAG pipeline as the app: get_rag_answer_params, build_rag_context,
prepare_ollama_messages, chat_client.chat. Returns result dicts compatible with the WebUI.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from application.rag.params import get_rag_answer_params
from application.rag.use_cases import build_rag_context, prepare_ollama_messages
from domain.entities.rag import RagQuestionRequest

from application.rag_tests.validator import validate_result


def run_one_test(
    test: dict[str, Any],
    model: str,
    *,
    collection_name: str | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """
    Run a single RAG test: build context, chat, validate.
    Returns (content, rag_metadata, result_dict).
    """
    question = (test.get("question") or "").strip()
    start_time = time.time()
    try:
        params, deps = get_rag_answer_params(collection_name=collection_name)
        ctx, _ = build_rag_context(
            question,
            deps.rag_repo,
            deps.embed_provider,
            deps.rerank_client,
            params.context_chunk_chars,
            params.context_total_chars,
        )
        rag_metadata: dict[str, Any] = {
            "chunks_info": ctx.chunks_info,
            "chunks_count": len(ctx.chunks_info),
        }
        req = RagQuestionRequest(
            messages=[{"role": "user", "content": question}],
            model=model,
            stream=False,
        )
        ollama_messages, use_model = prepare_ollama_messages(
            req,
            deps.rag_repo,
            deps.embed_provider,
            deps.rerank_client,
            params.system_prefix,
            params.system_suffix,
            params.context_chunk_chars,
            params.context_total_chars,
            params.confidence_threshold,
            params.model_name,
            rag_context=ctx,
        )
        content = deps.chat_client.chat(ollama_messages, use_model, stream=False, options=None)
        elapsed_ms = int((time.time() - start_time) * 1000)

        def _approx_tokens(text: str) -> int:
            if not text:
                return 0
            return max(1, int(len(text) / 4))

        prompt_text = question + (ctx.context_text or "")
        prompt_tokens = _approx_tokens(prompt_text)
        completion_tokens = _approx_tokens(content or "")
        total_tokens = prompt_tokens + completion_tokens

        validation = validate_result(test, content or "", rag_metadata)
        result: dict[str, Any] = {
            "test_id": test.get("id"),
            "test_name": test.get("name"),
            "platform": test.get("platform"),
            "framework": test.get("framework"),
            "model": model,
            "status": validation.get("status", "FAIL"),
            "response_time_ms": elapsed_ms,
            "latency_ms": elapsed_ms,
            "rag_used": validation.get("rag_used", False),
            "confidence_label": validation.get("confidence_label", ""),
            "missing_concepts": validation.get("missing_concepts") or [],
            "found_concepts": validation.get("found_concepts") or [],
            "full_response": content or None,
            "chunks_info": rag_metadata.get("chunks_info") or [],
            "retrieved_chunks": validation.get("retrieved_chunks"),
            "question": question,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "context_chars": len(ctx.context_text or ""),
        }
        if validation.get("failure_reason") is not None:
            result["failure_reason"] = validation["failure_reason"]
        return content or "", rag_metadata, result
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        result = {
            "test_id": test.get("id"),
            "test_name": test.get("name"),
            "platform": test.get("platform"),
            "framework": test.get("framework"),
            "model": model,
            "status": "FAIL",
            "response_time_ms": elapsed_ms,
            "latency_ms": elapsed_ms,
            "rag_used": False,
            "confidence_label": "0/0",
            "missing_concepts": test.get("expected_concepts") or [],
            "found_concepts": [],
            "full_response": None,
            "chunks_info": [],
            "retrieved_chunks": None,
            "question": question,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "context_chars": None,
            "failure_reason": str(e),
            "error": str(e),
        }
        return "", {}, result


def run_tests_sync(
    tests: list[dict[str, Any]],
    model: str,
    *,
    collection_name: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[dict[str, Any]]:
    """
    Run tests one by one synchronously. Optionally call on_progress(current_index, total, test_name).
    Returns list of result dicts.
    """
    total = len(tests)
    results: list[dict[str, Any]] = []
    for i, test in enumerate(tests):
        if on_progress:
            on_progress(i + 1, total, test.get("name") or test.get("id") or "")
        _, _, result = run_one_test(test, model, collection_name=collection_name)
        results.append(result)
    return results
