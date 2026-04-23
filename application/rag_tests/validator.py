"""
Validate RAG test run result: required concepts (any/all), confidence score, RAG usage.
"""

from __future__ import annotations

import os
import re
from typing import Any

from application.rag_tests.metrics import (
    CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION,
    CURRENT_RAG_TESTS_METRICS_VERSION,
)


def _normalize_whitespace(text: str) -> str:
    return " ".join((text or "").split())


def _response_contains_concept(response: str, concept: str) -> bool:
    """Case-insensitive check; treat concept as literal (can contain parens, etc.)."""
    if not response or not concept:
        return False
    pattern = re.escape(concept.strip())
    return bool(re.search(pattern, response, re.IGNORECASE))


def _matches_data_race(response: str, _concept: str) -> bool:
    r = response or ""
    if _response_contains_concept(r, "data race"):
        return True
    return bool(re.search(r"race\s+conditions?", r, re.IGNORECASE))


def _matches_weak_reference(response: str, _concept: str) -> bool:
    r = response or ""
    if _response_contains_concept(r, "weak reference"):
        return True
    low = r.lower()
    if "[weak" in low:
        return True
    if re.search(r"\bweak\s+var\b", r, re.IGNORECASE):
        return True
    if re.search(r"\bweak\s+let\b", r, re.IGNORECASE):
        return True
    return False


def _matches_id_colon(response: str, _concept: str) -> bool:
    r = response or ""
    if _response_contains_concept(r, "id:"):
        return True
    if re.search(r"\bid\s*:\s*", r, re.IGNORECASE):
        return True
    if re.search(r"identified\s+by", r, re.IGNORECASE):
        return True
    return False


def _matches_custom_layout(response: str, _concept: str) -> bool:
    r = response or ""
    if _response_contains_concept(r, "custom Layout") or _response_contains_concept(r, "custom layout"):
        return True
    low = r.lower()
    for needle in ("lazyvgrid", "lazyhgrid", "griditem", "layout protocol", "layout that"):
        if needle in low:
            return True
    return False


def _matches_slash_pair(response: str, concept: str) -> bool:
    """e.g. 'weak / unowned' — require evidence for each side."""
    r = response or ""
    parts = [p.strip() for p in concept.split(" / ") if p.strip()]
    if len(parts) < 2:
        return False
    for p in parts:
        pl = p.lower()
        if pl == "weak":
            if not (_matches_weak_reference(r, p) or re.search(r"\bweak\b", r, re.IGNORECASE)):
                return False
        elif pl == "unowned":
            if not re.search(r"\bunowned\b", r, re.IGNORECASE):
                return False
        elif not _response_contains_concept(r, p):
            return False
    return True


_SPECIAL_CHECKERS: list[tuple[str, Any]] = [
    ("data race", _matches_data_race),
    ("weak reference", _matches_weak_reference),
    ("id:", _matches_id_colon),
    ("custom layout", _matches_custom_layout),
]


def _checker_for_concept(concept: str) -> Any:
    key = concept.strip().lower()
    for prefix, fn in _SPECIAL_CHECKERS:
        if key == prefix:
            return fn
    if " / " in concept:
        return _matches_slash_pair
    return None


def concept_satisfied(response: str, concept: str) -> bool:
    """Literal substring match, plus built-in heuristics for known tricky concepts."""
    if not concept or not (concept.strip()):
        return True
    fn = _checker_for_concept(concept)
    if fn is not None:
        return bool(fn(response or "", concept))
    return _response_contains_concept(response or "", concept)


def validate_concepts(
    response: str,
    expected_concepts: list[str],
    concept_mode: str,
    *,
    concept_groups: list[list[str]] | None = None,
) -> tuple[bool, int, int, list[str]]:
    """
    Check which expected concepts appear in the response.
    Returns (passed, hits, total, missing_concepts).
    concept_mode: 'any' => at least one flat concept; 'all' => every flat concept.
    concept_groups: optional OR-groups; each group must have at least one match (AND across groups).
    """
    response = response or ""
    flat = [c for c in (expected_concepts or []) if isinstance(c, str) and c.strip()]
    groups = [
        [a.strip() for a in g if isinstance(a, str) and a.strip()]
        for g in (concept_groups or [])
        if isinstance(g, list)
    ]
    groups = [g for g in groups if g]

    flat_hits = sum(1 for c in flat if concept_satisfied(response, c))
    flat_missing = [c for c in flat if not concept_satisfied(response, c)]

    group_hits = 0
    group_missing: list[str] = []
    for gi, alts in enumerate(groups):
        if any(concept_satisfied(response, a) for a in alts):
            group_hits += 1
        else:
            group_missing.append(f"(group {gi + 1}: {' OR '.join(alts)})")

    total = len(flat) + len(groups)
    hits = flat_hits + group_hits

    if concept_mode == "any":
        flat_ok = (not flat) or (flat_hits >= 1)
    else:
        flat_ok = (not flat) or (flat_hits == len(flat))

    groups_ok = (not groups) or (group_hits == len(groups))
    passed = flat_ok and groups_ok

    if concept_mode == "any" and flat_ok:
        # Report which flat concepts were not found (informational) while still passing.
        missing = flat_missing + ([] if groups_ok else group_missing)
    elif not passed:
        missing = flat_missing + ([] if groups_ok else group_missing)
    else:
        missing = []
    return passed, hits, total, missing


def _found_flat_concepts(response: str, concepts: list[str]) -> list[str]:
    return [c for c in concepts if isinstance(c, str) and c.strip() and concept_satisfied(response, c)]


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
        short = _normalize_whitespace(text[:50])
        if len(short) >= 15 and short in norm_response:
            return True
    return False


def _extract_strict_quote(response: str) -> str | None:
    """Extract the first RAG QUOTE value from a model response."""
    if not response:
        return None
    patterns = [
        r"RAG\s+QUOTE\s*:\s*\"(?P<quote>.+?)\"",
        r"RAG\s+QUOTE\s*:\s*“(?P<quote>.+?)”",
        r"RAG\s+QUOTE\s*:\s*'(?P<quote>.+?)'",
        r"RAG\s+QUOTE\s*:\s*(?P<quote>[^\n\r]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        quote = (match.group("quote") or "").strip()
        quote = quote.strip("\"'“”")
        if quote:
            return quote
    return None


def _chunk_texts(chunks_info: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for chunk in chunks_info or []:
        if not isinstance(chunk, dict):
            continue
        for key in ("text", "text_preview", "content", "preview"):
            value = chunk.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value)
    return texts


def _quote_in_chunks(quote: str, chunks_info: list[dict[str, Any]], min_len: int = 20) -> bool:
    """Strict quote check: quoted text must be a non-trivial substring of retrieved chunk text."""
    q = (quote or "").strip()
    if len(q) < min_len:
        return False
    norm_quote = _normalize_whitespace(q)
    for text in _chunk_texts(chunks_info):
        if q in text:
            return True
        if norm_quote and norm_quote in _normalize_whitespace(text):
            return True
    return False


def validate_result(
    test: dict[str, Any],
    response_content: str,
    rag_metadata: dict[str, Any] | None,
    *,
    strict_mode: bool | None = None,
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
    concept_groups = test.get("concept_groups")
    if concept_groups is not None and not isinstance(concept_groups, list):
        concept_groups = None
    else:
        concept_groups = [
            [str(x).strip() for x in g if isinstance(x, str) and str(x).strip()]
            for g in (concept_groups or [])
            if isinstance(g, list)
        ]
        concept_groups = [g for g in concept_groups if g]

    concept_mode = (test.get("concept_mode") or "all").strip().lower()
    if concept_mode not in ("any", "all"):
        concept_mode = "all"
    require_rag = test.get("rag_requirement", True)
    # Backward compatibility: direct callers that don't pass strict_mode keep
    # the legacy per-test RAG Strict overlap behavior. New runners pass the
    # run-level flag explicitly; only strict_mode=True enables quote validation.
    run_strict_mode = bool(strict_mode) if strict_mode is not None else False
    require_rag_overlap = bool(test.get("rag_strict", False)) if strict_mode is None else bool(strict_mode)
    validation_mode = str(os.getenv("RAG_TESTS_VALIDATION_MODE", "strict") or "strict").strip().lower()
    if validation_mode not in ("balanced", "strict"):
        validation_mode = "balanced"
    balanced_mode = validation_mode == "balanced"

    concepts_passed, hits, total, missing = validate_concepts(
        response_content or "",
        concepts,
        concept_mode,
        concept_groups=concept_groups,
    )
    confidence_label = f"{hits}/{total} concepts found" if total else "N/A"
    missing_count = max(0, total - hits)

    chunks_info = (rag_metadata or {}).get("chunks_info") or []
    chunks_count = (rag_metadata or {}).get("chunks_count", len(chunks_info))
    rag_retrieved = chunks_count > 0
    rag_overlap = True
    strict_quote = _extract_strict_quote(response_content or "") if run_strict_mode else None
    strict_quote_ok: bool | None = None
    strict_quote_reason: str | None = None
    if run_strict_mode:
        if not rag_retrieved:
            rag_overlap = False
            strict_quote_ok = False
            strict_quote_reason = "RAG not retrieved; no chunk can validate the strict quote"
        elif not strict_quote:
            rag_overlap = False
            strict_quote_ok = False
            strict_quote_reason = "Missing RAG QUOTE block"
        elif not _quote_in_chunks(strict_quote, chunks_info):
            rag_overlap = False
            strict_quote_ok = False
            strict_quote_reason = "RAG QUOTE was not found verbatim in retrieved chunks"
        else:
            rag_overlap = True
            strict_quote_ok = True
            strict_quote_reason = "RAG QUOTE matched retrieved chunk text"
    elif require_rag_overlap and rag_retrieved and chunks_info:
        rag_overlap = _response_overlaps_chunks(response_content or "", chunks_info)

    empty = not (response_content or "").strip()
    min_length_ok = len((response_content or "").strip()) >= 10

    concepts_ok = concepts_passed if (concepts or concept_groups) else True
    # Default mode is intentionally less strict for RAG Tests:
    # for non-rag_strict tests, allow one missing concept as "good enough".
    if (
        balanced_mode
        and not require_rag_overlap
        and concept_mode == "all"
        and total > 0
        and missing_count <= 1
    ):
        concepts_ok = True

    rag_ok = (not require_rag) or rag_retrieved
    overlap_waived = False
    if require_rag and require_rag_overlap and rag_retrieved:
        rag_ok = rag_overlap
        # In balanced mode, don't fail a perfect concept answer only because
        # overlap heuristic didn't detect exact chunk snippets.
        if balanced_mode and not rag_overlap and concepts_ok and hits == total:
            rag_ok = True
            overlap_waived = True
    status = "PASS" if (concepts_ok and rag_ok and not empty and min_length_ok) else "FAIL"
    retrieval_used = bool(rag_retrieved)
    grounding_overlap = bool(rag_overlap) if require_rag_overlap and rag_retrieved else None
    strict_rag_ok = bool(rag_ok) if require_rag_overlap else None
    rag_used = retrieval_used

    response_norm = response_content or ""
    found_concepts = _found_flat_concepts(response_norm, [c for c in concepts if isinstance(c, str)])

    failure_reason: str | None = None
    if status == "FAIL":
        reasons: list[str] = []
        if not concepts_ok:
            reasons.append("Missing concepts: " + ", ".join(missing))
        if not rag_ok:
            if chunks_count == 0:
                reasons.append("RAG not triggered (no matching context found)")
            elif run_strict_mode and strict_quote_reason:
                reasons.append(strict_quote_reason)
            elif require_rag_overlap and chunks_info and not overlap_waived:
                reasons.append("RAG chunks did not overlap response")
            else:
                reasons.append("RAG was skipped by trigger/keywords or produced no usable chunks")
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
        "retrieval_used": retrieval_used,
        "grounding_overlap": grounding_overlap,
        "strict_rag_ok": strict_rag_ok,
        "strict_mode": run_strict_mode,
        "strict_quote": strict_quote,
        "strict_quote_ok": strict_quote_ok,
        "strict_quote_reason": strict_quote_reason,
        "metrics_version": CURRENT_RAG_TESTS_METRICS_VERSION,
        "evaluation_method_version": CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION,
        "confidence_label": confidence_label,
        "full_response": response_content if status == "FAIL" else None,
        "retrieved_chunks": chunks_info if status == "FAIL" and chunks_info else None,
    }
    if failure_reason is not None:
        out["failure_reason"] = failure_reason
    return out
