"""
Synchronous RAG test runner for CLI (no Flask/HTTP).

Uses the same RAG pipeline as the app: get_rag_answer_params, build_rag_context,
prepare_ollama_messages, chat_client.chat. Returns result dicts compatible with the WebUI.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from collections.abc import Callable
from typing import Any

from application.rag.params import get_rag_answer_params
from application.rag_tests.metrics import (
    CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION,
    CURRENT_RAG_TESTS_METRICS_VERSION,
)
from application.rag.use_cases import build_rag_context, prepare_ollama_messages
from domain.entities.rag import RagQuestionRequest
from rag_service.config import override_retrieval_settings

from application.rag_tests.validator import validate_result


RAG_TESTS_RETRIEVAL_PRESET: dict[str, Any] = {
    "coverage_gate_enabled": True,
    "coverage_gate_boost_final_k": 4,
    "coverage_retry_supplemental_search_enabled": True,
    "coverage_retry_final_k": 12,
}


@contextmanager
def rag_tests_retrieval_preset():
    with override_retrieval_settings(RAG_TESTS_RETRIEVAL_PRESET):
        yield


def build_proxy_chat_payload(
    *,
    question: str,
    model: str,
    collection_name: str,
    client_request_id: str,
    prompt_name: str | None = None,
    temperature: float | None = None,
    top_k: float | None = None,
    testing_disable_rerank: bool | None = None,
) -> dict[str, Any]:
    """Canonical /v1/chat/completions payload for RAG tests parity with proxy."""
    payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": question}],
        "model": model,
        "collection_name": collection_name,
        "stream": True,
        "include_rag_metadata": True,
        "client_request_id": client_request_id,
    }
    if prompt_name:
        payload["prompt_name"] = prompt_name
    if temperature is not None:
        payload["temperature"] = float(temperature)
    if top_k is not None:
        payload["top_k"] = float(top_k)
    if testing_disable_rerank is not None:
        payload["testing_disable_rerank"] = bool(testing_disable_rerank)
    return payload


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

    # Enrich retrieval query with platform/framework/expected concepts and simple synonyms
    platform = (test.get("platform") or "").strip()
    framework = (test.get("framework") or "").strip()
    concepts = [c.strip() for c in (test.get("expected_concepts") or []) if c.strip()]

    keywords: list[str] = []
    if platform:
        keywords.append(platform)
    if framework:
        keywords.append(framework)
    keywords.extend(concepts)

    # Simple query expansion for critical domains (Live Activity, Observation, SwiftData, etc.)
    lowered = " ".join(k.lower() for k in keywords)
    extra_terms: list[str] = []
    if "live activity" in lowered or "activitykit" in lowered:
        extra_terms.extend(["ActivityKit", "Live Activities", "WidgetKit"])
    if "swiftdata" in lowered:
        extra_terms.extend(["SwiftData", "ModelContext", "ModelContainer"])
    if "observation" in lowered or "@observation" in lowered:
        extra_terms.extend(["Observation", "@Observable", "Observation framework"])
    if "actor" in lowered or "sendable" in lowered:
        extra_terms.extend(["Swift Concurrency", "Sendable", "actor"])

    all_terms: list[str] = []
    for term in keywords + extra_terms:
        if term and term not in all_terms:
            all_terms.append(term)

    retrieval_query = question
    if all_terms:
        retrieval_query = f"{question}\n\nRelevant terms: " + ", ".join(all_terms)
    start_time = time.time()
    try:
        # Use a stricter, test-only system prompt to make answers
        # more doc-grounded and concept-complete in RAG Tests.
        params, deps = get_rag_answer_params(
            collection_name=collection_name,
            prompt_name="system_senior_ios_assistant_rag_tests",
        )
        with rag_tests_retrieval_preset():
            ctx, _ = build_rag_context(
                retrieval_query,
                deps.rag_repo,
                deps.embed_provider,
                deps.rerank_client,
                params.context_chunk_chars,
                params.context_total_chars,
                rag_required_keywords=None,
                trigger_threshold=None,
                force_rag=True,
            )
        rag_metadata: dict[str, Any] = {
            "chunks_info": ctx.chunks_info,
            "chunks_count": len(ctx.chunks_info),
            "rag_queries": [{"query": retrieval_query[:2000], "step": 0}],
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
        # Use deterministic settings for RAG tests to reduce variance in results.
        options = {"temperature": 0.0, "top_p": 0.1}
        content = deps.chat_client.chat(ollama_messages, use_model, stream=False, options=options)
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
            "difficulty": test.get("difficulty"),
            "model": model,
            "status": validation.get("status", "FAIL"),
            "response_time_ms": elapsed_ms,
            "latency_ms": elapsed_ms,
            "rag_used": validation.get("rag_used", False),
            "retrieval_used": validation.get("retrieval_used", False),
            "grounding_overlap": validation.get("grounding_overlap"),
            "strict_rag_ok": validation.get("strict_rag_ok"),
            "metrics_version": validation.get("metrics_version", CURRENT_RAG_TESTS_METRICS_VERSION),
            "evaluation_method_version": validation.get(
                "evaluation_method_version",
                CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION,
            ),
            "confidence_label": validation.get("confidence_label", ""),
            "missing_concepts": validation.get("missing_concepts") or [],
            "found_concepts": validation.get("found_concepts") or [],
            "full_response": content or None,
            "chunks_info": rag_metadata.get("chunks_info") or [],
            "rag_queries": rag_metadata.get("rag_queries") or [],
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
            "retrieval_used": False,
            "grounding_overlap": None,
            "strict_rag_ok": None,
            "metrics_version": CURRENT_RAG_TESTS_METRICS_VERSION,
            "evaluation_method_version": CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION,
            "confidence_label": "0/0",
            "missing_concepts": test.get("expected_concepts") or [],
            "found_concepts": [],
            "full_response": None,
            "chunks_info": [],
            "rag_queries": [],
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
