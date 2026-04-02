"""
Domain-level retrieval helpers for RAG.

This module contains the pure business logic used to:
- Normalize user questions into embedding/search queries.
- Detect version-focused questions.
- Decide when more chunks are needed.
- Build Qdrant metadata filters based on doc_type.
- Provide doc_type-based priority for sorting results.

All numeric/string thresholds and keyword lists are taken from the
configuration layer (`config`) with sensible defaults so the behavior
can be tuned without changing code.
"""

from __future__ import annotations

from typing import Any

import re

from domain.entities.rag import QueryIntent

from config import (  # type: ignore
    get_retrieval_bool,
    get_retrieval_dict,
    get_retrieval_int,
    get_retrieval_list,
)


# --- Configuration-backed constants -------------------------------------------------

_DEFAULT_STOP_WORDS: list[str] = [
    "please",
    "can you",
    "could you",
    "would you",
    "tell me",
    "explain",
    "show me",
    "give me",
    "how to",
    "how do",
    "what is",
    "what are",
]

RETRIEVAL_STOP_WORDS: tuple[str, ...] = tuple(
    get_retrieval_list("retrieval_stop_words", _DEFAULT_STOP_WORDS)
)

DOC_TYPE_PREFERRED_FOR_QA: tuple[str, ...] = tuple(
    get_retrieval_list(
        "doc_type_preferred_for_qa",
        ["conceptual", "overview", "tutorial", "documentation", "howto"],
    )
)

DOC_TYPE_WEIGHT: dict[str, int] = get_retrieval_dict(
    "doc_type_weight",
    {
        "conceptual": 3,
        "overview": 2,
        "tutorial": 1,
        "documentation": 1,
        "howto": 1,
        "release_notes": -2,
        "news": -2,
    },
)

DOC_SCOPE_PREFERRED_FOR_QA: tuple[str, ...] = tuple(
    get_retrieval_list(
        "doc_scope_preferred_for_qa",
        ["api_symbol", "guide", "tutorial"],
    )
)

DOC_SCOPE_WEIGHT: dict[str, int] = get_retrieval_dict(
    "doc_scope_weight",
    {
        "api_symbol": 2,
        "guide": 1,
        "tutorial": 1,
        "discussion": 0,
        "articles": 0,
        "books": 0,
        "forums": -1,
    },
)

# Concept/topic aliases for query expansion. Keys are lowercased phrases that,
# when present in the normalized question, should bias retrieval toward more
# specific documentation regions. Values are additional tokens appended to the
# retrieval query. Backed by config so hosts can tune behavior without code changes.
_DEFAULT_CONCEPT_ALIASES: dict[str, str] = {
    # Observation framework / Observable macro in UIKit and SwiftUI.
    # These aliases avoid hardcoding a single Apple doc URL while still
    # steering the embedding toward the relevant documentation cluster.
    "observable macro": " observation tracking observation framework updating views automatically with observation tracking ",
    "observable": " observation tracking observation framework ",
    "observation tracking": " observation tracking observation framework ",
}
CONCEPT_ALIASES: dict[str, str] = get_retrieval_dict(
    "concept_aliases",
    _DEFAULT_CONCEPT_ALIASES,
)

MULTI_CHUNK_KEYWORDS: tuple[str, ...] = tuple(
    get_retrieval_list(
        "multi_chunk_keywords",
        [
            "compare",
            "comparison",
            "difference",
            "explain fully",
            "fully explain",
            "lifecycle",
            "all ways",
            "all options",
            "list all",
            "step by step",
            "overview of",
        ],
    )
)

RERANK_MAX_CANDIDATES: int = get_retrieval_int("rerank_max_candidates", 12)
FINAL_CONTEXT_K: int = get_retrieval_int("final_context_k", 4)
# Slightly higher default for multi-chunk retrieval to better support broad domains (SwiftUI, Swift Concurrency).
MULTI_CHUNK_TOP_K: int = get_retrieval_int("multi_chunk_top_k", 24)
MULTI_CHUNK_FINAL_K: int = get_retrieval_int("multi_chunk_final_k", 8)

MAX_EMBED_TEXT_LENGTH: int = get_retrieval_int("max_embed_text_length", 400)

_DEFAULT_SKIP_GREETINGS: list[str] = [
    "hi",
    "hello",
    "hey",
]
SKIP_RAG_GREETINGS: tuple[str, ...] = tuple(
    get_retrieval_list("skip_rag_greetings", _DEFAULT_SKIP_GREETINGS)
)

_DEFAULT_RAG_REQUIRED_KEYWORDS: list[str] = [
    "swift",
    "swiftui",
    "uikit",
    "objective-c",
    "objc",
    "xcode",
    "ios",
    "macos",
    "combine",
    "cocoa",
    "appkit",
    "watchos",
    "tvos",
    "uiviewcontroller",
    "view model",
    "project",
    "codebase",
    "repository",
    "our code",
    "analyze",
    "review this code",
    "explain this code",
    "code snippet",
    "observation",
    "observable",
    "observation tracking",
]
RAG_REQUIRED_KEYWORDS: tuple[str, ...] = tuple(
    get_retrieval_list("rag_required_keywords", _DEFAULT_RAG_REQUIRED_KEYWORDS)
)

# RAG trigger (skip/run decision) delegated to rag_trigger module
from domain.services.rag_trigger import should_skip_rag_search as _should_skip_rag_search


def should_skip_rag_search(
    question: str,
    rag_required_keywords: list[str] | None = None,
    trigger_threshold: int | None = None,
) -> bool:
    """Delegate to rag_trigger. True when RAG should be skipped (greeting or score < threshold)."""
    return _should_skip_rag_search(
        question,
        rag_required_keywords=rag_required_keywords,
        trigger_threshold=trigger_threshold,
    )


_IOS_VERSION_Q_RE = re.compile(r"\biOS\s+(\d+(?:\.\d+)*)", re.IGNORECASE)
_SWIFT_VERSION_Q_RE = re.compile(r"\bSwift\s+(\d+(?:\.\d+)*)", re.IGNORECASE)

# API symbols: PascalCase / CamelCase type names (UIViewController, ContentUnavailableView, NSViewRepresentable).
# First segment may be all-caps (UI, NS); then at least one [A-Z][a-z0-9]+ segment.
_API_SYMBOL_RE = re.compile(r"[A-Z][a-zA-Z0-9]*(?:[A-Z][a-z0-9]+)+")


def parse_versions_from_question(question: str) -> tuple[list[str], list[str]]:
    """
    Extract explicit iOS/Swift versions mentioned in the question.

    Returns:
        (ios_versions, swift_versions) as sorted unique lists.
    """
    ios = {m.group(1) for m in _IOS_VERSION_Q_RE.finditer(question or "")}
    swift = {m.group(1) for m in _SWIFT_VERSION_Q_RE.finditer(question or "")}
    return sorted(ios), sorted(swift)


def is_version_question(question: str) -> bool:
    """
    True if the question is about Swift/iOS version / latest release.

    Heuristics:
    - Contains explicit version markers (\"iOS 18\", \"Swift 6.0\" etc.).
    - Or contains words like \"version\", \"latest\".
    """
    q = (question or "").lower()
    has_keywords = (
        "version" in q or "latest" in q
    )
    ios_q, swift_q = parse_versions_from_question(question)
    return has_keywords or bool(ios_q) or bool(swift_q)


def query_for_retrieval(question: str) -> str:
    """
    Build a query string suitable for vector search.

    Responsibilities:
    - Strip code blocks (```swift ... ```), they only waste embedding budget.
    - Remove generic greetings / filler phrases using RETRIEVAL_STOP_WORDS.
    - Bias toward UIKit vs SwiftUI when clearly specified.
    - Add extra version-related tokens for version questions.
    - Limit final length for the embedding model.
    """
    q_raw = (question or "").strip()

    # Remove fenced code blocks and leftover ``` markers.
    q_raw = re.sub(r"```[\w]*\n.*?```", "", q_raw, flags=re.DOTALL)
    q_raw = re.sub(r"```", "", q_raw)

    q = q_raw.lower()
    for w in RETRIEVAL_STOP_WORDS:
        q = q.replace(w, " ")
    q = " ".join(q.split()).strip().lstrip(".,;:!? ")
    if len(q) < 3:
        # Very short query: fall back to generic \"Swift documentation\" prefix.
        return "Swift documentation " + q_raw[:MAX_EMBED_TEXT_LENGTH]

    out = q if len(q) >= 5 else (q_raw + " " + q)

    # Bias retrieval toward the requested UI framework when clearly stated.
    if "uikit" in q and "swiftui" not in q:
        out = out + " UIKit UIViewController UIView"
    elif "swiftui" in q and "uikit" not in q:
        out = out + " SwiftUI View"

    # Concept/topic aliases: when the normalized question contains certain
    # phrases (e.g. Observable macro), append configured bias tokens.
    if CONCEPT_ALIASES:
        q_compact = f" {q} "
        for alias, expansion in CONCEPT_ALIASES.items():
            a = (alias or "").strip().lower()
            if not a:
                continue
            if f" {a} " in q_compact:
                out = f"{out} {expansion}".strip()

    # For version questions, bias retrieval toward version/release chunks.
    ios_q, swift_q = parse_versions_from_question(question)
    if ios_q or swift_q or "version" in q_raw.lower() or "latest" in q_raw.lower():
        extra_parts: list[str] = []
        for v in swift_q:
            extra_parts.append(f"Swift {v} version RELEASE")
        for v in ios_q:
            extra_parts.append(f"iOS {v} version RELEASE")
        if not extra_parts:
            extra_parts.append("Swift version release number RELEASE")
        out = out + " " + " ".join(extra_parts)

    # Query expansion for API symbols: push embedding toward API-doc region (symbol names match chunks).
    symbols = list(dict.fromkeys(_API_SYMBOL_RE.findall(q_raw)))
    if symbols:
        expansion: list[str] = [out]
        for sym in symbols:
            expansion.append(sym)
            expansion.append(f"Swift {sym}")
            expansion.append(f"SwiftUI {sym}")
            expansion.append(f"API {sym}")
        out = " ".join(expansion)

    if len(out) > MAX_EMBED_TEXT_LENGTH:
        out = out[:MAX_EMBED_TEXT_LENGTH]
    return out


def need_more_chunks(question: str) -> bool:
    """
    True if the question likely needs multiple chunks (compare, lifecycle, list all etc.).
    """
    q = (question or "").lower()
    return any(kw in q for kw in MULTI_CHUNK_KEYWORDS)


def build_qdrant_filter(question: str) -> dict[str, Any] | None:
    """
    Build Qdrant metadata filter for doc_type- and doc_scope-preferred retrieval.

    Behavior:
    - For version questions, returns None (version-focused search is handled separately).
    - Otherwise, returns a \"should\" filter so points with doc_type in DOC_TYPE_PREFERRED_FOR_QA
      or doc_scope in DOC_SCOPE_PREFERRED_FOR_QA are preferred.
    """
    if is_version_question(question):
        return None
    conditions: list[dict[str, Any]] = []
    for dt in DOC_TYPE_PREFERRED_FOR_QA:
        conditions.append({"key": "doc_type", "match": {"value": dt}})
    for ds in DOC_SCOPE_PREFERRED_FOR_QA:
        conditions.append({"key": "doc_scope", "match": {"value": ds}})
    if not conditions:
        return None
    return {"should": conditions}


def merge_qdrant_filters(
    base: dict[str, Any] | None,
    extra: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    AND-combine Qdrant filter dicts for retrieval.

    ``base`` is typically ``build_qdrant_filter(question)`` (a ``should`` clause on
    doc_type / doc_scope). ``extra`` is caller-supplied (e.g. section_path constraint).
    When both are set, both sub-filters must match (nested under ``must``).

    Build ``extra`` using Qdrant's filter schema, or use
    ``extra_filter_section_path_joined_equals`` when payloads include
    ``section_path_joined`` (WebUI markdown ingest and web UI collection indexing).
    """
    if not base:
        return extra
    if not extra:
        return base
    return {"must": [base, extra]}


def extra_filter_section_path_joined_equals(joined: str) -> dict[str, Any] | None:
    """
    Build an ``extra`` filter: payload field ``section_path_joined`` must exactly equal ``joined``.
    Format must match the indexer (colon-separated headings, e.g. ``"Concurrency:Actors"``).
    Returns None if ``joined`` is empty (no constraint).
    """
    j = (joined or "").strip()
    if not j:
        return None
    return {"must": [{"key": "section_path_joined", "match": {"value": j}}]}


def extra_filter_symbol_equals(symbol: str | None) -> dict[str, Any] | None:
    """
    Extra filter requiring payload ``symbol`` to equal the given value.
    Returns None when symbol is empty.
    """
    s = (symbol or "").strip()
    if not s:
        return None
    return {"must": [{"key": "symbol", "match": {"value": s}}]}


def extra_filter_framework_equals(framework: str | None) -> dict[str, Any] | None:
    """
    Extra filter requiring payload ``framework`` to equal the given value.
    Returns None when framework is empty.
    """
    f = (framework or "").strip().lower()
    if not f:
        return None
    return {"must": [{"key": "framework", "match": {"value": f}}]}


def doc_type_priority(hit: dict[str, Any]) -> int:
    """
    Compute priority score for a hit based on its doc_type.

    Higher scores mean the document type is preferred for Q&A (conceptual docs,
    overviews, tutorials) versus low-value types like release notes or news.
    """
    payload = hit.get("payload") or {}
    doc_type = (payload.get("doc_type") or "documentation").lower()
    return int(DOC_TYPE_WEIGHT.get(doc_type, 0))


def doc_scope_priority(hit: dict[str, Any]) -> int:
    """
    Compute priority score for a hit based on its doc_scope (source type).

    Higher scores mean the source type is preferred for Q&A (api_symbol, guide,
    tutorial) versus lower-value types like forums or unknown.
    """
    payload = hit.get("payload") or {}
    doc_scope = (payload.get("doc_scope") or "").lower()
    return int(DOC_SCOPE_WEIGHT.get(doc_scope, 0))


def combined_doc_priority(hit: dict[str, Any]) -> int:
    """Combined priority from doc_type and doc_scope for sorting retrieval results."""
    return doc_type_priority(hit) + doc_scope_priority(hit)


def intent_match_priority(hit: dict[str, Any], intent: QueryIntent | None) -> int:
    """
    Additional priority from intent match (symbol/framework/section).

    This is added on top of combined_doc_priority when QueryIntent is available.
    """
    if intent is None:
        return 0
    payload = hit.get("payload") or {}
    score = 0
    symbol = (payload.get("symbol") or "").strip()
    framework = (payload.get("framework") or "").strip().lower()
    section = (payload.get("section") or "").strip().lower()
    if intent.symbol and symbol and intent.symbol == symbol:
        score += 4
    if intent.framework and framework and intent.framework == intent.framework.lower():
        score += 2
    if intent.section_hint and section and intent.section_hint.lower() == section:
        score += 1
    return score


def infer_query_intent(question: str) -> QueryIntent:
    """
    Infer QueryIntent from the raw question text.

    - symbol: first API-like symbol (PascalCase / CamelCase) when present.
    - framework: detected high-level framework/technology (uikit, swiftui, combine, observation).
    - section_hint: simple hint for section type (discussion/overview/examples).
    """
    q_raw = (question or "").strip()
    q_lower = q_raw.lower()

    # Symbol: first API-like token; skip very short ones to avoid obvious noise.
    symbol: str | None = None
    for match in _API_SYMBOL_RE.findall(q_raw):
        if len(match) >= 4:
            symbol = match
            break

    framework: str | None = None
    if "uikit" in q_lower:
        framework = "uikit"
    elif "swiftui" in q_lower:
        framework = "swiftui"
    elif "combine" in q_lower:
        framework = "combine"
    elif "observation" in q_lower or "@observable" in q_lower or "observable" in q_lower:
        # Observation framework / Observable macro in Swift.
        framework = "observation"

    section_hint: str | None = None
    if "пример" in q_lower or "example" in q_lower or "sample" in q_lower:
        section_hint = "example"
    elif "как работает" in q_lower or "how does" in q_lower or "how it works" in q_lower:
        section_hint = "discussion"
    elif "overview" in q_lower:
        section_hint = "overview"

    return QueryIntent(symbol=symbol, framework=framework, section_hint=section_hint)


def expand_query_variants(question: str) -> list[str]:
    """
    Build 1..N alternate query strings for retrieval (abbreviation expansion, etc.).
    When expansion is disabled, returns a single-element list with the original question.
    """
    q = (question or "").strip()
    if not q:
        return []
    if not get_retrieval_bool("query_expansion_enabled", False):
        return [q]
    max_v = max(1, get_retrieval_int("query_expansion_max_variants", 3))
    abbrev = get_retrieval_dict("query_expansion_abbreviations", {})
    variants: list[str] = [q]
    qlower = q.lower()
    for trigger, expansion in abbrev.items():
        trig = str(trigger).strip()
        if not trig or trig.lower() not in qlower:
            continue
        extra = f"{q} {expansion}".strip()
        if extra not in variants:
            variants.append(extra)
        if len(variants) >= max_v:
            break
    return variants[:max_v]


def rrf_merge_hit_lists(
    ranked_lists: list[list[dict[str, Any]]],
    *,
    limit: int,
    k: int = 60,
) -> list[dict[str, Any]]:
    """
    Reciprocal rank fusion: merge several ranked hit lists, deduplicating by point id.
    """
    scores: dict[Any, float] = {}
    payloads: dict[Any, dict[str, Any]] = {}
    for hits in ranked_lists:
        for rank, h in enumerate(hits, start=1):
            hid = h.get("id")
            if hid is None:
                continue
            scores[hid] = scores.get(hid, 0.0) + 1.0 / (k + rank)
            if hid not in payloads:
                payloads[hid] = h
    merged_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:limit]
    out: list[dict[str, Any]] = []
    for hid in merged_ids:
        base = dict(payloads[hid])
        base["score"] = scores[hid]
        out.append(base)
    return out


__all__ = [
    "RETRIEVAL_STOP_WORDS",
    "DOC_TYPE_PREFERRED_FOR_QA",
    "DOC_TYPE_WEIGHT",
    "DOC_SCOPE_PREFERRED_FOR_QA",
    "DOC_SCOPE_WEIGHT",
    "MULTI_CHUNK_KEYWORDS",
    "RERANK_MAX_CANDIDATES",
    "FINAL_CONTEXT_K",
    "MULTI_CHUNK_TOP_K",
    "MULTI_CHUNK_FINAL_K",
    "MAX_EMBED_TEXT_LENGTH",
    "SKIP_RAG_GREETINGS",
    "RAG_REQUIRED_KEYWORDS",
    "parse_versions_from_question",
    "is_version_question",
    "should_skip_rag_search",
    "query_for_retrieval",
    "need_more_chunks",
    "build_qdrant_filter",
    "merge_qdrant_filters",
    "extra_filter_section_path_joined_equals",
    "extra_filter_symbol_equals",
    "extra_filter_framework_equals",
    "doc_type_priority",
    "doc_scope_priority",
    "combined_doc_priority",
    "intent_match_priority",
    "infer_query_intent",
    "expand_query_variants",
    "rrf_merge_hit_lists",
]

