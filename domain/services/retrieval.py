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

from config import (  # type: ignore
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
    "что такое",
    "как",
    "объясни",
    "покажи",
    "дай",
    "расскажи",
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

MULTI_CHUNK_KEYWORDS: tuple[str, ...] = tuple(
    get_retrieval_list(
        "multi_chunk_keywords",
        [
            "compare",
            "comparison",
            "сравни",
            "сравнение",
            "difference",
            "разница",
            "explain fully",
            "fully explain",
            "подробно объясни",
            "lifecycle",
            "жизненный цикл",
            "all ways",
            "all options",
            "все способы",
            "list all",
            "перечисли все",
            "step by step",
            "пошагово",
            "overview of",
            "обзор",
        ],
    )
)

RERANK_MAX_CANDIDATES: int = get_retrieval_int("rerank_max_candidates", 12)
FINAL_CONTEXT_K: int = get_retrieval_int("final_context_k", 4)
MULTI_CHUNK_TOP_K: int = get_retrieval_int("multi_chunk_top_k", 16)
MULTI_CHUNK_FINAL_K: int = get_retrieval_int("multi_chunk_final_k", 8)

MAX_EMBED_TEXT_LENGTH: int = get_retrieval_int("max_embed_text_length", 400)

_DEFAULT_SKIP_GREETINGS: list[str] = [
    "hi",
    "hello",
    "hey",
    "привет",
    "здравствуй",
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
    "наш проект",
    "репозиторий",
    "analyze",
    "review this code",
    "explain this code",
    "разбери",
    "проанализируй",
    "code snippet",
    "этот код",
    "код",
    "observation",
    "observable",
    "observation tracking",
]
RAG_REQUIRED_KEYWORDS: tuple[str, ...] = tuple(
    get_retrieval_list("rag_required_keywords", _DEFAULT_RAG_REQUIRED_KEYWORDS)
)


_IOS_VERSION_Q_RE = re.compile(r"\biOS\s+(\d+(?:\.\d+)*)", re.IGNORECASE)
_SWIFT_VERSION_Q_RE = re.compile(r"\bSwift\s+(\d+(?:\.\d+)*)", re.IGNORECASE)


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
    - Or contains words like \"version\", \"версия\", \"latest\", \"последняя\".
    """
    q = (question or "").lower()
    has_keywords = (
        "версия" in q or "version" in q or "последняя" in q or "latest" in q
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

    # For version questions, bias retrieval toward version/release chunks.
    ios_q, swift_q = parse_versions_from_question(question)
    if ios_q or swift_q or "версия" in q_raw.lower() or "version" in q_raw.lower() or "последняя" in q_raw.lower():
        extra_parts: list[str] = []
        for v in swift_q:
            extra_parts.append(f"Swift {v} version RELEASE")
        for v in ios_q:
            extra_parts.append(f"iOS {v} version RELEASE")
        if not extra_parts:
            extra_parts.append("Swift version release number RELEASE")
        out = out + " " + " ".join(extra_parts)

    if len(out) > MAX_EMBED_TEXT_LENGTH:
        out = out[:MAX_EMBED_TEXT_LENGTH]
    return out


def should_skip_rag_search(
    question: str,
    rag_required_keywords: list[str] | None = None,
) -> bool:
    """
    True when RAG should be skipped: greeting (exact match) or no RAG-required
    keyword in the query (not about project, Apple tech, or code analysis).
    If rag_required_keywords is provided, use it (normalized to lower); else use RAG_REQUIRED_KEYWORDS.
    """
    q = (question or "").strip().lower()
    if not q:
        return False
    if q in SKIP_RAG_GREETINGS:
        return True
    keywords = (
        [k.lower() for k in (rag_required_keywords or []) if k]
        if rag_required_keywords is not None
        else RAG_REQUIRED_KEYWORDS
    )
    if not any(kw in q for kw in keywords):
        return True
    return False


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
    "doc_type_priority",
    "doc_scope_priority",
    "combined_doc_priority",
]

