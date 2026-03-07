"""
Domain-level retrieval helpers for RAG.

Pure business logic: query normalization, version detection, Qdrant filters, doc_type priority.
Config is loaded from project root config when run from repo.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from config import get_retrieval_dict, get_retrieval_int, get_retrieval_list
except ImportError:
    get_retrieval_dict = lambda k, d: d  # noqa: E731
    get_retrieval_int = lambda k, d: d  # noqa: E731
    get_retrieval_list = lambda k, d: d  # noqa: E731

_DEFAULT_STOP_WORDS: list[str] = [
    "please", "can you", "could you", "would you", "tell me", "explain",
    "show me", "give me", "how to", "how do", "what is", "what are",
    "что такое", "как", "объясни", "покажи", "дай", "расскажи",
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
        "conceptual": 3, "overview": 2, "tutorial": 1, "documentation": 1,
        "howto": 1, "release_notes": -2, "news": -2,
    },
)
MULTI_CHUNK_KEYWORDS: tuple[str, ...] = tuple(
    get_retrieval_list(
        "multi_chunk_keywords",
        [
            "compare", "comparison", "сравни", "разница", "difference",
            "explain fully", "lifecycle", "all ways", "list all", "step by step", "overview of",
        ],
    )
)
RERANK_MAX_CANDIDATES: int = get_retrieval_int("rerank_max_candidates", 12)
FINAL_CONTEXT_K: int = get_retrieval_int("final_context_k", 4)
MULTI_CHUNK_TOP_K: int = get_retrieval_int("multi_chunk_top_k", 16)
MULTI_CHUNK_FINAL_K: int = get_retrieval_int("multi_chunk_final_k", 8)
MAX_EMBED_TEXT_LENGTH: int = get_retrieval_int("max_embed_text_length", 400)
SKIP_RAG_GREETINGS: tuple[str, ...] = tuple(
    get_retrieval_list("skip_rag_greetings", ["hi", "hello", "hey", "привет", "здравствуй"])
)
_DEFAULT_RAG_REQUIRED: list[str] = [
    "swift", "swiftui", "uikit", "ios", "macos", "xcode", "combine", "observation",
    "code", "analyze", "explain this code", "код", "наш проект",
]
RAG_REQUIRED_KEYWORDS: tuple[str, ...] = tuple(
    get_retrieval_list("rag_required_keywords", _DEFAULT_RAG_REQUIRED)
)

_IOS_VERSION_Q_RE = re.compile(r"\biOS\s+(\d+(?:\.\d+)*)", re.IGNORECASE)
_SWIFT_VERSION_Q_RE = re.compile(r"\bSwift\s+(\d+(?:\.\d+)*)", re.IGNORECASE)


def parse_versions_from_question(question: str) -> tuple[list[str], list[str]]:
    """Extract explicit iOS/Swift versions from question. Returns (ios_versions, swift_versions)."""
    ios = {m.group(1) for m in _IOS_VERSION_Q_RE.finditer(question or "")}
    swift = {m.group(1) for m in _SWIFT_VERSION_Q_RE.finditer(question or "")}
    return sorted(ios), sorted(swift)


def is_version_question(question: str) -> bool:
    """True if question is about Swift/iOS version or latest release."""
    q = (question or "").lower()
    has_kw = "версия" in q or "version" in q or "последняя" in q or "latest" in q
    ios_q, swift_q = parse_versions_from_question(question)
    return has_kw or bool(ios_q) or bool(swift_q)


def query_for_retrieval(question: str) -> str:
    """Build query string for vector search: strip code blocks, stop words, limit length."""
    q_raw = (question or "").strip()
    q_raw = re.sub(r"```[\w]*\n.*?```", "", q_raw, flags=re.DOTALL)
    q_raw = re.sub(r"```", "", q_raw)
    q = q_raw.lower()
    for w in RETRIEVAL_STOP_WORDS:
        q = q.replace(w, " ")
    q = " ".join(q.split()).strip().lstrip(".,;:!? ")
    if len(q) < 3:
        return "Swift documentation " + q_raw[:MAX_EMBED_TEXT_LENGTH]
    out = q if len(q) >= 5 else (q_raw + " " + q)
    if "uikit" in q and "swiftui" not in q:
        out = out + " UIKit UIViewController UIView"
    elif "swiftui" in q and "uikit" not in q:
        out = out + " SwiftUI View"
    ios_q, swift_q = parse_versions_from_question(question)
    if ios_q or swift_q or "версия" in q_raw.lower() or "version" in q_raw.lower():
        extra = []
        for v in swift_q:
            extra.append(f"Swift {v} version RELEASE")
        for v in ios_q:
            extra.append(f"iOS {v} version RELEASE")
        if not extra:
            extra.append("Swift version release number RELEASE")
        out = out + " " + " ".join(extra)
    if len(out) > MAX_EMBED_TEXT_LENGTH:
        out = out[:MAX_EMBED_TEXT_LENGTH]
    return out


def should_skip_rag_search(question: str) -> bool:
    """True when RAG should be skipped: greeting or no RAG-required keyword."""
    q = (question or "").strip().lower()
    if not q:
        return False
    if q in SKIP_RAG_GREETINGS:
        return True
    if not any(kw in q for kw in RAG_REQUIRED_KEYWORDS):
        return True
    return False


def need_more_chunks(question: str) -> bool:
    """True if question likely needs multiple chunks."""
    q = (question or "").lower()
    return any(kw in q for kw in MULTI_CHUNK_KEYWORDS)


def build_qdrant_filter(question: str) -> dict[str, Any] | None:
    """Build Qdrant metadata filter for doc_type preference. None for version questions."""
    if is_version_question(question):
        return None
    if not DOC_TYPE_PREFERRED_FOR_QA:
        return None
    conditions = [
        {"key": "doc_type", "match": {"value": dt}}
        for dt in DOC_TYPE_PREFERRED_FOR_QA
    ]
    if not conditions:
        return None
    return {"should": conditions}


def doc_type_priority(hit: dict[str, Any]) -> int:
    """Priority score for hit by doc_type (higher = preferred for Q&A)."""
    payload = hit.get("payload") or {}
    doc_type = (payload.get("doc_type") or "documentation").lower()
    return int(DOC_TYPE_WEIGHT.get(doc_type, 0))


__all__ = [
    "RETRIEVAL_STOP_WORDS", "DOC_TYPE_PREFERRED_FOR_QA", "DOC_TYPE_WEIGHT",
    "MULTI_CHUNK_KEYWORDS", "RERANK_MAX_CANDIDATES", "FINAL_CONTEXT_K",
    "MULTI_CHUNK_TOP_K", "MULTI_CHUNK_FINAL_K", "MAX_EMBED_TEXT_LENGTH",
    "SKIP_RAG_GREETINGS", "RAG_REQUIRED_KEYWORDS",
    "parse_versions_from_question", "is_version_question", "should_skip_rag_search",
    "query_for_retrieval", "need_more_chunks", "build_qdrant_filter", "doc_type_priority",
]
