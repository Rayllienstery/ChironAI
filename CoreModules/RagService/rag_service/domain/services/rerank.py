"""
Domain-level rerank helpers.

Pure business logic for:
- Building the rerank prompt text (question + numbered candidate snippets).
- Parsing the LLM response (JSON array of 1-based indices).
- Reordering hits by parsed order and appending any missing.
- Applying rank-based scores (1/rank) and trimming to final_k.

No HTTP or infrastructure here; callers use this to prepare input and process output.
"""

from __future__ import annotations

import json
import re
from typing import Any


def shorten_for_rerank(text: str, max_len: int = 300) -> str:
    """
    Truncate candidate text for inclusion in the rerank prompt.
    Preserves at most max_len characters; appends ellipsis if truncated.
    """
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "\u2026"


def build_rerank_prompt(
    question: str,
    candidate_texts: list[tuple[int, str]],
    max_snippet_len: int = 300,
) -> str:
    """
    Build the prompt string sent to the rerank LLM.

    candidate_texts: list of (1-based_index, text) for each candidate.
    Returns a single string (English instructions + question + numbered snippets).
    """
    lines: list[str] = []
    for idx, txt in candidate_texts:
        snippet = shorten_for_rerank(txt, max_snippet_len)
        lines.append(f"{idx}: {snippet}")
    numbered_chunks = "\n\n".join(lines)
    return f"""You have a question and several documentation excerpts.
Your task is to sort the excerpts by relevance to the question.
When two excerpts are similarly useful, prefer the one that adds a different angle or topic so that the top entries together cover more distinct aspects of the question (avoid redundant near-duplicates at the top).

Question:
{question}

Excerpts (each with a number):
{numbered_chunks}

Reply ONLY with a single JSON array of excerpt numbers in descending order of relevance.
Allowed examples:
[2, 1, 3]
[1, 2]
If some numbers are not present, simply omit them.
Do not add any text before or after the JSON."""


def extract_candidates_from_rerank_prompt(prompt_text: str) -> list[tuple[int, str]]:
    """
    Extract (1-based_index, snippet_text) from the build_rerank_prompt output.

    This is used to adapt Ollama native /api/rerank which expects separate
    documents rather than a single JSON-ordered prompt.
    """
    text = (prompt_text or "").strip()
    if not text:
        return []

    marker = "Excerpts (each with a number):"
    if marker in text:
        text = text.split(marker, 1)[1]

    # build_rerank_prompt ends with "Reply ONLY with a single JSON array ..."
    if "Reply ONLY" in text:
        text = text.split("Reply ONLY", 1)[0]

    segments = [s.strip() for s in text.split("\n\n") if s.strip()]
    out: list[tuple[int, str]] = []
    for seg in segments:
        m = re.match(r"^\s*(\d+)\s*:\s*(.*)\s*$", seg, flags=re.DOTALL)
        if not m:
            continue
        idx = int(m.group(1))
        snippet = (m.group(2) or "").strip()
        if idx > 0 and snippet:
            out.append((idx, snippet))
    return out


def native_rerank_response_to_order(raw_response: dict[str, Any]) -> list[int] | None:
    """
    Convert Ollama native /api/rerank response to a ranked order list.

    Expected response shape:
    {
      "results": [{"document": "IDX1: ...", "relevance_score": ...}, ...]
    }
    """
    if not raw_response:
        return None
    results = raw_response.get("results") or []
    if not isinstance(results, list):
        return None

    order: list[int] = []
    seen: set[int] = set()
    idx_re = re.compile(r"^\s*IDX(\d+)\s*:", flags=re.IGNORECASE)
    for r in results:
        if not isinstance(r, dict):
            continue
        doc = r.get("document") or ""
        m = idx_re.match(str(doc))
        if not m:
            continue
        idx = int(m.group(1))
        if idx not in seen:
            order.append(idx)
            seen.add(idx)

    return order or None


def parse_rerank_order(raw_response: str) -> list[int] | None:
    """
    Parse the rerank LLM response into a list of 1-based indices.

    Returns None if parsing fails or result is not a list (caller keeps original order).
    """
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
    """
    Reorder candidates by order_1based (1-based indices), append any not in order,
    then append the rest of all_hits (beyond candidates).

    candidates: first N hits (e.g. RERANK_MAX_CANDIDATES).
    order_1based: list of 1-based indices (e.g. [2, 1, 3]).
    all_hits: full list; candidates = all_hits[:len(candidates)] typically.
    Returns new list: reordered candidates by order_1based, then remaining from all_hits.
    """
    if not candidates:
        return list(all_hits)
    indexed = {i + 1: h for i, h in enumerate(candidates)}
    seen_ids: set[int] = set()
    new_order: list[dict[str, Any]] = []
    for n in order_1based:
        h = indexed.get(n)
        if h is not None and id(h) not in seen_ids:
            new_order.append(h)
            seen_ids.add(id(h))
    for h in candidates:
        if id(h) not in seen_ids:
            new_order.append(h)
    if len(all_hits) > len(candidates):
        new_order.extend(all_hits[len(candidates) :])
    return new_order


def assign_rerank_scores(hits: list[dict[str, Any]]) -> None:
    """Set each hit's rerank_score to 1 / rank (1-based) over the full ordered list."""
    for rank, hit in enumerate(hits, start=1):
        hit["rerank_score"] = 1.0 / rank


def apply_rerank_scores_and_cut(
    hits: list[dict[str, Any]],
    final_k: int,
) -> list[dict[str, Any]]:
    """
    Annotate each hit with rerank_score = 1 / rank (1-based rank),
    then return the first final_k hits.
    """
    if not hits:
        return []
    assign_rerank_scores(hits)
    return hits[:final_k]


__all__ = [
    "shorten_for_rerank",
    "build_rerank_prompt",
    "extract_candidates_from_rerank_prompt",
    "native_rerank_response_to_order",
    "parse_rerank_order",
    "reorder_hits_by_indices",
    "assign_rerank_scores",
    "apply_rerank_scores_and_cut",
]
