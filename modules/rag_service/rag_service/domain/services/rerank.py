"""
Domain-level rerank helpers.

Pure logic: build rerank prompt, parse LLM response, reorder hits, apply scores.
"""

from __future__ import annotations

import json
from typing import Any


def shorten_for_rerank(text: str, max_len: int = 300) -> str:
    """Truncate candidate text for rerank prompt."""
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "\u2026"


def build_rerank_prompt(
    question: str,
    candidate_texts: list[tuple[int, str]],
    max_snippet_len: int = 300,
) -> str:
    """Build prompt string for rerank LLM. candidate_texts: list of (1-based_index, text)."""
    lines = [f"{idx}: {shorten_for_rerank(txt, max_snippet_len)}" for idx, txt in candidate_texts]
    numbered = "\n\n".join(lines)
    return f"""You have a question and several documentation excerpts.
Your task is to sort the excerpts by relevance to the question.

Question:
{question}

Excerpts (each with a number):
{numbered}

Reply ONLY with a single JSON array of excerpt numbers in descending order of relevance.
Examples: [2, 1, 3] or [1, 2]. Do not add any text before or after the JSON."""


def parse_rerank_order(raw_response: str) -> list[int] | None:
    """Parse rerank LLM response into list of 1-based indices. None on failure."""
    raw = (raw_response or "").strip()
    if not raw:
        return None
    try:
        order = json.loads(raw)
        if not isinstance(order, list):
            return None
        return [int(x) for x in order if isinstance(x, (int, float))]
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def reorder_hits_by_indices(
    candidates: list[dict[str, Any]],
    order_1based: list[int],
    all_hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reorder candidates by order_1based, append missing, then rest of all_hits."""
    if not candidates:
        return list(all_hits)
    indexed = {i + 1: h for i, h in enumerate(candidates)}
    seen = set()
    new_order = []
    for n in order_1based:
        h = indexed.get(n)
        if h is not None and id(h) not in seen:
            new_order.append(h)
            seen.add(id(h))
    for h in candidates:
        if id(h) not in seen:
            new_order.append(h)
    if len(all_hits) > len(candidates):
        new_order.extend(all_hits[len(candidates) :])
    return new_order


def apply_rerank_scores_and_cut(
    hits: list[dict[str, Any]],
    final_k: int,
) -> list[dict[str, Any]]:
    """Annotate each hit with rerank_score = 1/rank, return first final_k."""
    if not hits:
        return []
    for rank, hit in enumerate(hits, start=1):
        hit["rerank_score"] = 1.0 / rank
    return hits[:final_k]


__all__ = [
    "shorten_for_rerank", "build_rerank_prompt", "parse_rerank_order",
    "reorder_hits_by_indices", "apply_rerank_scores_and_cut",
]
