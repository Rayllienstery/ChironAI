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
from typing import Any, Dict, List, Tuple


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
    candidate_texts: List[Tuple[int, str]],
    max_snippet_len: int = 300,
) -> str:
    """
    Build the prompt string sent to the rerank LLM.

    candidate_texts: list of (1-based_index, text) for each candidate.
    Returns a single string (Russian instructions + question + numbered snippets).
    """
    lines: List[str] = []
    for idx, txt in candidate_texts:
        snippet = shorten_for_rerank(txt, max_snippet_len)
        lines.append(f"{idx}: {snippet}")
    numbered_chunks = "\n\n".join(lines)
    return f"""У тебя есть вопрос и несколько фрагментов документации.
Твоя задача — отсортировать фрагменты по релевантности к вопросу.

Вопрос:
{question}

Фрагменты (каждый с номером):
{numbered_chunks}

Ответь ТОЛЬКО одним JSON-массивом номеров фрагментов в порядке убывания релевантности.
Примеры допустимых ответов:
[2, 1, 3]
[1, 2]
Если какие‑то номера отсутствуют, просто не включай их.
Не добавляй никакого текста до или после JSON."""


def parse_rerank_order(raw_response: str) -> List[int] | None:
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
    candidates: List[Dict[str, Any]],
    order_1based: List[int],
    all_hits: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
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
    new_order: List[Dict[str, Any]] = []
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


def apply_rerank_scores_and_cut(
    hits: List[Dict[str, Any]],
    final_k: int,
) -> List[Dict[str, Any]]:
    """
    Annotate each hit with rerank_score = 1 / rank (1-based rank),
    then return the first final_k hits.
    """
    if not hits:
        return []
    for rank, hit in enumerate(hits, start=1):
        hit["rerank_score"] = 1.0 / rank
    return hits[:final_k]


__all__ = [
    "shorten_for_rerank",
    "build_rerank_prompt",
    "parse_rerank_order",
    "reorder_hits_by_indices",
    "apply_rerank_scores_and_cut",
]
