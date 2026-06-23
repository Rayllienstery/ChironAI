"""
Shared metric/version helpers for RAG test results and runs.
"""

from __future__ import annotations

from typing import Any

CURRENT_RAG_TESTS_METRICS_VERSION = "v2_retrieval_grounding_split_2026_04_23"
CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION = CURRENT_RAG_TESTS_METRICS_VERSION
LEGACY_RAG_TESTS_METRICS_VERSION = "legacy_unknown"
LEGACY_RAG_TESTS_EVALUATION_METHOD_VERSION = "legacy_unknown"


def normalize_rag_test_result(result: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(result or {})
    metrics_version = str(out.get("metrics_version") or "").strip() or LEGACY_RAG_TESTS_METRICS_VERSION
    evaluation_method_version = (
        str(out.get("evaluation_method_version") or "").strip()
        or (
            CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION
            if metrics_version != LEGACY_RAG_TESTS_METRICS_VERSION
            else LEGACY_RAG_TESTS_EVALUATION_METHOD_VERSION
        )
    )

    retrieval_used_raw = out.get("retrieval_used")
    if retrieval_used_raw is None:
        chunks_info = out.get("chunks_info")
        if isinstance(chunks_info, list):
            retrieval_used = len(chunks_info) > 0
        else:
            chunks_count = out.get("chunks_count")
            if chunks_count is not None:
                try:
                    retrieval_used = int(chunks_count) > 0
                except (TypeError, ValueError):
                    retrieval_used = bool(out.get("rag_used"))
            else:
                retrieval_used = bool(out.get("rag_used"))
    else:
        retrieval_used = bool(retrieval_used_raw)

    grounding_overlap = out.get("grounding_overlap")
    if grounding_overlap is not None:
        grounding_overlap = bool(grounding_overlap)

    strict_rag_ok = out.get("strict_rag_ok")
    if strict_rag_ok is not None:
        strict_rag_ok = bool(strict_rag_ok)

    strict_mode = bool(out.get("strict_mode", False))
    strict_quote = out.get("strict_quote")
    if strict_quote is not None:
        strict_quote = str(strict_quote)
    strict_quote_ok = out.get("strict_quote_ok")
    if strict_quote_ok is not None:
        strict_quote_ok = bool(strict_quote_ok)
    strict_quote_reason = out.get("strict_quote_reason")
    if strict_quote_reason is not None:
        strict_quote_reason = str(strict_quote_reason)

    out["metrics_version"] = metrics_version
    out["evaluation_method_version"] = evaluation_method_version
    out["retrieval_used"] = retrieval_used
    out["grounding_overlap"] = grounding_overlap
    out["strict_rag_ok"] = strict_rag_ok
    out["strict_mode"] = strict_mode
    out["strict_quote"] = strict_quote
    out["strict_quote_ok"] = strict_quote_ok
    out["strict_quote_reason"] = strict_quote_reason

    # Compatibility alias: new runs use rag_used == retrieval_used.
    if metrics_version != LEGACY_RAG_TESTS_METRICS_VERSION or "rag_used" not in out:
        out["rag_used"] = retrieval_used

    return out


def normalize_rag_test_run(run: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(run or {})
    raw_results = out.get("results")
    results = [
        normalize_rag_test_result(item)
        for item in raw_results
        if isinstance(item, dict)
    ] if isinstance(raw_results, list) else []
    out["results"] = results

    metrics_version = str(out.get("metrics_version") or "").strip()
    evaluation_method_version = str(out.get("evaluation_method_version") or "").strip()

    if not metrics_version and results:
        versions = {str(r.get("metrics_version") or "").strip() for r in results if str(r.get("metrics_version") or "").strip()}
        if len(versions) == 1:
            metrics_version = next(iter(versions))
    if not evaluation_method_version and results:
        versions = {
            str(r.get("evaluation_method_version") or "").strip()
            for r in results
            if str(r.get("evaluation_method_version") or "").strip()
        }
        if len(versions) == 1:
            evaluation_method_version = next(iter(versions))

    out["metrics_version"] = metrics_version or LEGACY_RAG_TESTS_METRICS_VERSION
    out["evaluation_method_version"] = (
        evaluation_method_version
        or (
            CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION
            if out["metrics_version"] != LEGACY_RAG_TESTS_METRICS_VERSION
            else LEGACY_RAG_TESTS_EVALUATION_METHOD_VERSION
        )
    )
    return out


__all__ = [
    "CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION",
    "CURRENT_RAG_TESTS_METRICS_VERSION",
    "LEGACY_RAG_TESTS_EVALUATION_METHOD_VERSION",
    "LEGACY_RAG_TESTS_METRICS_VERSION",
    "normalize_rag_test_result",
    "normalize_rag_test_run",
]
