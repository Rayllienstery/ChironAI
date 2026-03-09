"""
Validate RAG test run result: required concepts (any/all), confidence score, RAG usage.
"""

from __future__ import annotations

import re
from typing import Any


def _normalize_whitespace(text: str) -> str:
    return " ".join((text or "").split())


def _response_contains_concept(response: str, concept: str) -> bool:
    """Case-insensitive check; treat concept as literal (can contain parens, etc.)."""
    if not response or not concept:
        return False
    # Escape special regex chars for literal match; then search case-insensitive
    pattern = re.escape(concept.strip())
    return bool(re.search(pattern, response, re.IGNORECASE))


def validate_concepts(
    response: str,
    expected_concepts: list[str],
    concept_mode: str,
) -> tuple[bool, int, int, list[str]]:
    """
    Check which expected concepts appear in the response.
    Returns (passed, hits, total, missing_concepts).
    concept_mode: 'any' => at least one; 'all' => all must appear.
    """
    if not expected_concepts:
        return True, 0, 0, []
    hits = sum(1 for c in expected_concepts if _response_contains_concept(response, c))
    total = len(expected_concepts)
    missing = [c for c in expected_concepts if not _response_contains_concept(response, c)]
    if concept_mode == "any":
        passed = hits >= 1
    else:
        passed = hits == total
    return passed, hits, total, missing


def _response_overlaps_chunks(response: str, chunks_info: list[dict[str, Any]], min_len: int = 20) -> bool:
    """Heuristic: response contains a non-trivial substring from at least one chunk."""
    if not response or not chunks_info:
        return False
    norm_response = _normalize_whitespace(response)
    for chunk in chunks_info:
        text = (chunk.get("text_preview") or chunk.get("text") or "").strip()
        if not text or len(text) < min_len:
            continue
        snippet = _normalize_whitespace(text[:300])
        if snippet and snippet in norm_response:
            return True
        # Try first 50 chars as substring
        short = _normalize_whitespace(text[:50])
        if len(short) >= 15 and short in norm_response:
            return True
    return False


def validate_result(
    test: dict[str, Any],
    response_content: str,
    rag_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Validate a single test run.
    test: parsed test dict (question, expected_concepts, concept_mode, rag_requirement, rag_strict, etc.)
    response_content: full assistant message text
    rag_metadata: from chat response (chunks_info, chunks_count, etc.) or None

    Returns result dict: status (PASS/FAIL), concept_hits, concept_total, missing_concepts,
    rag_used, confidence_label, retrieved_chunks (for FAIL), full_response (for FAIL).
    """
    concepts = test.get("expected_concepts") or []
    concept_mode = (test.get("concept_mode") or "all").strip().lower()
    if concept_mode not in ("any", "all"):
        concept_mode = "all"
    require_rag = test.get("rag_requirement", True)
    require_rag_overlap = test.get("rag_strict", False)

    # Concept validation
    concepts_passed, hits, total, missing = validate_concepts(
        response_content or "",
        concepts,
        concept_mode,
    )
    confidence_label = f"{hits}/{total} concepts found" if total else "N/A"

    # RAG usage
    chunks_info = (rag_metadata or {}).get("chunks_info") or []
    chunks_count = (rag_metadata or {}).get("chunks_count", len(chunks_info))
    rag_used = chunks_count > 0
    if require_rag_overlap and rag_used and chunks_info:
        rag_used = _response_overlaps_chunks(response_content or "", chunks_info)

    # Empty or irrelevant
    empty = not (response_content or "").strip()
    min_length_ok = len((response_content or "").strip()) >= 10

    # Overall pass/fail
    rag_ok = (not require_rag) or rag_used
    concepts_ok = concepts_passed if concepts else True
    status = "PASS" if (concepts_ok and rag_ok and not empty and min_length_ok) else "FAIL"

    # Found concepts: expected concepts that appear in the response
    response_norm = response_content or ""
    found_concepts = [c for c in concepts if _response_contains_concept(response_norm, c)]

    # Failure reason when FAIL
    failure_reason: str | None = None
    if status == "FAIL":
        reasons: list[str] = []
        if not concepts_ok:
            reasons.append("Missing concepts: " + ", ".join(missing))
        if not rag_ok:
            if require_rag_overlap and chunks_count > 0 and chunks_info:
                reasons.append("RAG chunks did not overlap response")
            else:
                reasons.append("RAG not triggered")
        if empty:
            reasons.append("Response empty")
        if not empty and not min_length_ok:
            reasons.append("Response too short")
        failure_reason = "; ".join(reasons) if reasons else None

    out: dict[str, Any] = {
        "status": status,
        "concept_hits": hits,
        "concept_total": total,
        "missing_concepts": missing if status == "FAIL" else [],
        "found_concepts": found_concepts,
        "rag_used": rag_used,
        "confidence_label": confidence_label,
        "full_response": response_content if status == "FAIL" else None,
        "retrieved_chunks": chunks_info if status == "FAIL" and chunks_info else None,
    }
    if failure_reason is not None:
        out["failure_reason"] = failure_reason
    return out
