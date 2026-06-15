"""
Synchronous RAG test runner for CLI (no Flask/HTTP).

Uses the same RAG pipeline as the app: get_rag_answer_params, build_rag_context,
prepare_ollama_messages, chat_client.chat. Returns result dicts compatible with the WebUI.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from rag_service.application.params import get_rag_answer_params
from rag_service.application.use_cases import build_rag_context, prepare_ollama_messages
from rag_service.config import override_retrieval_settings
from rag_service.domain.entities import RagQuestionRequest

from application.rag_tests.metrics import (
    CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION,
    CURRENT_RAG_TESTS_METRICS_VERSION,
)
from application.rag_tests.validator import validate_result

STRICT_RAG_QUOTE_INSTRUCTION = """RAG Tests Strict Mode is enabled.
You must include exactly one line near the top of the answer in this form:
RAG QUOTE: "..."
The quoted text must be copied verbatim from the retrieved RAG context. Use a complete, natural fragment of at least 20 characters. After that quote, answer the user's question normally. If the retrieved context is missing or irrelevant, write:
RAG QUOTE: ""
and state that the indexed context did not contain a suitable quote."""


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


def build_test_messages(question: str, *, strict_mode: bool = False) -> list[dict[str, str]]:
    """Build canonical OpenAI-format messages for a RAG test request."""
    messages: list[dict[str, str]] = []
    if strict_mode:
        messages.append({"role": "system", "content": STRICT_RAG_QUOTE_INSTRUCTION})
    messages.append({"role": "user", "content": question})
    return messages


def build_test_retrieval_query(test: dict[str, Any]) -> str:
    """Build the retrieval query used by RAG tests from a markdown test case."""
    question = (test.get("question") or "").strip()

    platform = (test.get("platform") or "").strip()
    framework = (test.get("framework") or "").strip()
    concepts = [c.strip() for c in (test.get("expected_concepts") or []) if c.strip()]

    keywords: list[str] = []
    if platform:
        keywords.append(platform)
    if framework:
        keywords.append(framework)
    keywords.extend(concepts)

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

    if all_terms:
        return f"{question}\n\nRelevant terms: " + ", ".join(all_terms)
    return question


def build_proxy_chat_payload(
    *,
    question: str,
    model: str,
    provider_id: str | None = None,
    collection_name: str,
    client_request_id: str,
    prompt_name: str | None = None,
    temperature: float | None = None,
    top_k: float | None = None,
    testing_disable_rerank: bool | None = None,
    strict_mode: bool = False,
) -> dict[str, Any]:
    """Canonical /v1/chat/completions payload for RAG tests parity with proxy."""
    payload: dict[str, Any] = {
        "messages": build_test_messages(question, strict_mode=strict_mode),
        "model": model,
        "collection_name": collection_name,
        "stream": True,
        "include_rag_metadata": True,
        "client_request_id": client_request_id,
        "strict_mode": bool(strict_mode),
    }
    if provider_id:
        payload["provider_id"] = provider_id
    if prompt_name:
        payload["prompt_name"] = prompt_name
    if temperature is not None:
        payload["temperature"] = float(temperature)
    if top_k is not None:
        payload["top_k"] = float(top_k)
    if testing_disable_rerank is not None:
        payload["testing_disable_rerank"] = bool(testing_disable_rerank)
    return payload


def _result_metric_fields(validation: dict[str, Any] | None) -> dict[str, Any]:
    validation = validation or {}
    return {
        "rag_used": bool(validation.get("rag_used", False)),
        "retrieval_used": bool(validation.get("retrieval_used", False)),
        "grounding_overlap": validation.get("grounding_overlap"),
        "strict_rag_ok": validation.get("strict_rag_ok"),
        "strict_mode": bool(validation.get("strict_mode", False)),
        "strict_quote": validation.get("strict_quote"),
        "strict_quote_ok": validation.get("strict_quote_ok"),
        "strict_quote_reason": validation.get("strict_quote_reason"),
        "metrics_version": validation.get("metrics_version", CURRENT_RAG_TESTS_METRICS_VERSION),
        "evaluation_method_version": validation.get(
            "evaluation_method_version",
            CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION,
        ),
    }


def build_rag_test_result(
    *,
    test: dict[str, Any],
    model: str,
    provider_id: str | None = None,
    content: str,
    rag_metadata: dict[str, Any] | None,
    validation: dict[str, Any],
    response_time_ms: int,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    tokens_per_second_generated: float | None = None,
    tokens_per_second_total: float | None = None,
    context_chars: int | None = None,
    rag_timings: dict[str, Any] | None = None,
    trace_steps: list[dict[str, Any]] | None = None,
    order: int | None = None,
) -> dict[str, Any]:
    """Canonical result shape shared by CLI and WebUI RAG test runners."""
    rag_metadata = rag_metadata or {}
    result: dict[str, Any] = {
        "test_id": test.get("id"),
        "test_name": test.get("name"),
        "platform": test.get("platform"),
        "framework": test.get("framework"),
        "difficulty": test.get("difficulty"),
        "model": model,
        "provider_id": str(provider_id or "").strip() or None,
        "status": validation.get("status", "FAIL"),
        "response_time_ms": response_time_ms,
        "latency_ms": latency_ms if latency_ms is not None else response_time_ms,
        **_result_metric_fields(validation),
        "confidence_label": validation.get("confidence_label", ""),
        "missing_concepts": validation.get("missing_concepts") or [],
        "found_concepts": validation.get("found_concepts") or [],
        "full_response": content or None,
        "chunks_info": rag_metadata.get("chunks_info") or [],
        "rag_queries": rag_metadata.get("rag_queries") or [],
        "retrieved_chunks": validation.get("retrieved_chunks"),
        "question": test.get("question") or "",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "tokens_per_second_generated": tokens_per_second_generated,
        "tokens_per_second_total": tokens_per_second_total,
        "context_chars": context_chars,
        "rag_timings": rag_timings,
        "trace_steps": trace_steps or [],
    }
    if order is not None:
        result["_order"] = order
    if validation.get("failure_reason") is not None:
        result["failure_reason"] = validation["failure_reason"]
    return result


def build_rag_test_error_result(
    *,
    test: dict[str, Any],
    model: str,
    provider_id: str | None = None,
    error: Any,
    response_time_ms: int = 0,
    order: int | None = None,
    strict_mode: bool = False,
) -> dict[str, Any]:
    """Canonical failed result when the runner could not obtain a model response."""
    result: dict[str, Any] = {
        "test_id": test.get("id"),
        "test_name": test.get("name"),
        "platform": test.get("platform"),
        "framework": test.get("framework"),
        "difficulty": test.get("difficulty"),
        "model": model,
        "provider_id": str(provider_id or "").strip() or None,
        "status": "FAIL",
        "response_time_ms": response_time_ms,
        "latency_ms": response_time_ms,
        "rag_used": False,
        "retrieval_used": False,
        "grounding_overlap": None,
        "strict_rag_ok": None,
        "strict_mode": bool(strict_mode),
        "strict_quote": None,
        "strict_quote_ok": None,
        "strict_quote_reason": None,
        "metrics_version": CURRENT_RAG_TESTS_METRICS_VERSION,
        "evaluation_method_version": CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION,
        "confidence_label": "0/0",
        "missing_concepts": test.get("expected_concepts") or [],
        "found_concepts": [],
        "full_response": None,
        "chunks_info": [],
        "rag_queries": [],
        "retrieved_chunks": None,
        "question": test.get("question") or "",
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "tokens_per_second_generated": None,
        "tokens_per_second_total": None,
        "context_chars": None,
        "rag_timings": None,
        "trace_steps": [],
        "failure_reason": str(error),
        "error": str(error),
    }
    if order is not None:
        result["_order"] = order
    return result


def run_one_test(
    test: dict[str, Any],
    model: str,
    *,
    collection_name: str | None = None,
    strict_mode: bool = False,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """
    Run a single RAG test: build context, chat, validate.
    Returns (content, rag_metadata, result_dict).
    """
    question = (test.get("question") or "").strip()
    retrieval_query = build_test_retrieval_query(test)
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
            messages=build_test_messages(question, strict_mode=strict_mode),
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

        validation = validate_result(test, content or "", rag_metadata, strict_mode=strict_mode)
        result = build_rag_test_result(
            test=test,
            model=model,
            content=content or "",
            rag_metadata=rag_metadata,
            validation=validation,
            response_time_ms=elapsed_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            context_chars=len(ctx.context_text or ""),
        )
        return content or "", rag_metadata, result
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        result = build_rag_test_error_result(
            test=test,
            model=model,
            error=e,
            response_time_ms=elapsed_ms,
            strict_mode=strict_mode,
        )
        return "", {}, result


def run_tests_sync(
    tests: list[dict[str, Any]],
    model: str,
    *,
    collection_name: str | None = None,
    strict_mode: bool = False,
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
        _, _, result = run_one_test(test, model, collection_name=collection_name, strict_mode=strict_mode)
        results.append(result)
    return results
