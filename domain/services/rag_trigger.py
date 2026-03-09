"""
RAG trigger: scoring heuristic to decide when to run RAG search.

Uses keyword match, code patterns (CamelCase, snake_case, code blocks, API signatures),
technical phrases (strong/weak with word-boundary), and file extensions.
Greeting skip only when exact match + short message + no technical tokens.
Returns (score, signals, triggered) for structured logging.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from config import get_retrieval_int, get_retrieval_list
except ImportError:
    get_retrieval_int = lambda k, d: d  # noqa: E731
    get_retrieval_list = lambda k, d: d  # noqa: E731


# --- Config -----------------------------------------------------------------

_DEFAULT_GREETINGS = ["hi", "hello", "hey", "привет", "здравствуй", "good morning", "good evening"]
SKIP_RAG_GREETINGS: tuple[str, ...] = tuple(
    get_retrieval_list("skip_rag_greetings", _DEFAULT_GREETINGS)
)
SKIP_RAG_GREETING_MAX_LENGTH: int = get_retrieval_int("skip_rag_greeting_max_length", 30)
RAG_TRIGGER_THRESHOLD: int = get_retrieval_int("rag_trigger_threshold", 2)

_DEFAULT_STRONG: list[str] = [
    "compile", "runtime", "API", "framework", "syntax", "deprecated", "migration",
    "error", "bug", "architecture", "документация", "реализовать", "ошибка", "баг", "архитектура",
]
_DEFAULT_WEAK: list[str] = [
    "how does", "best practice", "pattern", "algorithm", "refactor", "unit test",
    "dependency", "library", "integration test",
]
RAG_TRIGGER_PHRASES_STRONG: tuple[str, ...] = tuple(
    get_retrieval_list("rag_trigger_technical_phrases_strong", _DEFAULT_STRONG)
)
RAG_TRIGGER_PHRASES_WEAK: tuple[str, ...] = tuple(
    get_retrieval_list("rag_trigger_technical_phrases_weak", _DEFAULT_WEAK)
)

# File extensions and code keywords (fixed lists)
_FILE_EXTENSIONS = ("swift", "m", "h", "py", "js", "ts", "go", "rs", "cpp", "java", "kt")
_CODE_KEYWORDS = ("func", "class", "struct", "protocol", "enum", "extension", "actor", "let", "var")

# Weights
WEIGHT_KEYWORD = 3
WEIGHT_CAMELCASE = 2
WEIGHT_SNAKE_CASE = 1
WEIGHT_CODE_BLOCK = 4
WEIGHT_CODE_KEYWORD = 4
WEIGHT_API_SIGNATURE = 2
WEIGHT_FILE_EXTENSION = 2
WEIGHT_PHRASE_STRONG = 2
WEIGHT_PHRASE_WEAK = 1

# Min length for API name to count (avoid f(), g())
API_SIGNATURE_MIN_NAME_LEN = 3


# --- Compiled regexes (once at import) ---------------------------------------

# CamelCase: SwiftUI, URLSession, UIViewController, XCTestCase (first segment: 2+ caps or PascalCase; rest: cap + optional alnum)
_RE_CAMELCASE = re.compile(r"(?:[A-Z]{2,}|[A-Z][a-z]+)(?:[A-Z][a-z0-9]*)+")
# snake_case: one underscore ok — load_data, fetch_user, get_user (in get_user_id)
_RE_SNAKE_CASE = re.compile(r"[a-z]+_[a-z]+")
# Code block
_RE_CODE_BLOCK = re.compile(r"```")
# Code keywords (Swift)
_RE_CODE_KEYWORD = re.compile(
    r"\b(func|class|struct|protocol|enum|extension|actor|let|var)\b",
    re.IGNORECASE,
)
# API signature: name(...); we'll filter by len(name) > 2
_RE_API_SIGNATURE = re.compile(r"(\w+)\([^)]*\)")
# File extension
_RE_FILE_EXTENSION = re.compile(
    r"\.(swift|m|h|py|js|ts|go|rs|cpp|java|kt)\b",
    re.IGNORECASE,
)


def _phrase_to_word_boundary_regex(phrase: str) -> re.Pattern[str]:
    """Build word-boundary regex for a phrase (tokenized match; multi-word as \\s+)."""
    escaped = re.escape(phrase.strip())
    # Allow internal spaces as whitespace
    pattern = r"\b" + re.sub(r"\\\s+", r"\\s+", escaped) + r"\b"
    return re.compile(pattern, re.IGNORECASE)


# Precompile phrase regexes for strong/weak (at module load)
_PHRASE_STRONG_REGEXES: tuple[re.Pattern[str], ...] = tuple(
    _phrase_to_word_boundary_regex(p) for p in RAG_TRIGGER_PHRASES_STRONG if p.strip()
)
_PHRASE_WEAK_REGEXES: tuple[re.Pattern[str], ...] = tuple(
    _phrase_to_word_boundary_regex(p) for p in RAG_TRIGGER_PHRASES_WEAK if p.strip()
)


def _get_keywords(rag_required_keywords: list[str] | None) -> list[str]:
    """Return normalized keyword list; when None, load from config."""
    if rag_required_keywords is not None:
        return [k.lower() for k in rag_required_keywords if k]
    default = get_retrieval_list("rag_required_keywords", [])
    return [k.lower() for k in default if k]


def _score_keyword(q_lower: str, keywords: list[str]) -> tuple[int, list[str]]:
    if not keywords:
        return 0, []
    for kw in keywords:
        if kw in q_lower:
            return WEIGHT_KEYWORD, ["keyword"]
    return 0, []


def _score_camelcase(q: str) -> tuple[int, list[str]]:
    if _RE_CAMELCASE.search(q):
        return WEIGHT_CAMELCASE, ["camelcase"]
    return 0, []


def _score_snake_case(q_lower: str) -> tuple[int, list[str]]:
    if _RE_SNAKE_CASE.search(q_lower):
        return WEIGHT_SNAKE_CASE, ["snake_case"]
    return 0, []


def _score_code_block(q: str) -> tuple[int, list[str]]:
    if _RE_CODE_BLOCK.search(q):
        return WEIGHT_CODE_BLOCK, ["code_block"]
    return 0, []


def _score_code_keyword(q_lower: str) -> tuple[int, list[str]]:
    if _RE_CODE_KEYWORD.search(q_lower):
        return WEIGHT_CODE_KEYWORD, ["code_keyword"]
    return 0, []


def _score_api_signature(q: str) -> tuple[int, list[str]]:
    for m in _RE_API_SIGNATURE.finditer(q):
        name = m.group(1)
        if len(name) > API_SIGNATURE_MIN_NAME_LEN:
            return WEIGHT_API_SIGNATURE, ["api_signature"]
    return 0, []


def _score_file_extension(q_lower: str) -> tuple[int, list[str]]:
    if _RE_FILE_EXTENSION.search(q_lower):
        return WEIGHT_FILE_EXTENSION, ["file_extension"]
    return 0, []


def _score_phrase_strong(q_lower: str) -> tuple[int, list[str]]:
    for rx in _PHRASE_STRONG_REGEXES:
        if rx.search(q_lower):
            return WEIGHT_PHRASE_STRONG, ["technical_phrase_strong"]
    return 0, []


def _score_phrase_weak(q_lower: str) -> tuple[int, list[str]]:
    for rx in _PHRASE_WEAK_REGEXES:
        if rx.search(q_lower):
            return WEIGHT_PHRASE_WEAK, ["technical_phrase_weak"]
    return 0, []


def compute_rag_trigger_score(
    question: str,
    rag_required_keywords: list[str] | None = None,
    trigger_threshold: int | None = None,
) -> tuple[int, list[str], bool]:
    """
    Compute RAG trigger score and signals. Lowercase is applied once and reused.

    Returns:
        (score, signals, triggered) where triggered = (score >= threshold).
    """
    q_raw = (question or "").strip()
    q_lower = q_raw.lower()
    if not q_raw:
        return 0, [], False

    threshold = trigger_threshold if trigger_threshold is not None else RAG_TRIGGER_THRESHOLD
    keywords = _get_keywords(rag_required_keywords)
    score = 0
    signals: list[str] = []

    # Keyword (+3)
    s, sig = _score_keyword(q_lower, keywords)
    if s:
        score += s
        signals.extend(sig)

    # CamelCase (+2) — use raw so we see UIViewController
    s, sig = _score_camelcase(q_raw)
    if s:
        score += s
        signals.extend(sig)

    # snake_case (+1)
    s, sig = _score_snake_case(q_lower)
    if s:
        score += s
        signals.extend(sig)

    # Code block (+4)
    s, sig = _score_code_block(q_raw)
    if s:
        score += s
        signals.extend(sig)

    # Code keyword (+4)
    s, sig = _score_code_keyword(q_lower)
    if s:
        score += s
        signals.extend(sig)

    # API signature (+2), len(name) > 2
    s, sig = _score_api_signature(q_raw)
    if s:
        score += s
        signals.extend(sig)

    # File extension (+2)
    s, sig = _score_file_extension(q_lower)
    if s:
        score += s
        signals.extend(sig)

    # Strong phrase (+2), word-boundary
    s, sig = _score_phrase_strong(q_lower)
    if s:
        score += s
        signals.extend(sig)

    # Weak phrase (+1), word-boundary
    s, sig = _score_phrase_weak(q_lower)
    if s:
        score += s
        signals.extend(sig)

    triggered = score >= threshold
    return score, signals, triggered


def _is_greeting_skip(
    q_raw: str, q_lower: str, keywords: list[str], trigger_threshold: int | None = None
) -> bool:
    """
    True if we should skip as greeting: normalized message equals a greeting and is short.
    Short exact greeting (e.g. "HELLO" or "  hello  ") skips even if it matches CamelCase.
    """
    if q_lower not in (g.lower().strip() for g in SKIP_RAG_GREETINGS):
        return False
    if len(q_raw) > SKIP_RAG_GREETING_MAX_LENGTH:
        return False
    # Optional: require no technical tokens so "hello SwiftUI" does not skip. For a single-word
    # greeting like "HELLO", we skip regardless of CamelCase score.
    score, _, _ = compute_rag_trigger_score(q_raw, rag_required_keywords=keywords, trigger_threshold=trigger_threshold)
    if score > 0 and len(q_raw.split()) > 1:
        return False  # multi-word with technical signal → do not skip
    return True


def should_skip_rag_search(
    question: str,
    rag_required_keywords: list[str] | None = None,
    trigger_threshold: int | None = None,
) -> bool:
    """
    True when RAG should be skipped.

    Skip if: greeting (exact + short + no technical tokens) OR trigger score < threshold.
    """
    q_raw = (question or "").strip()
    q_lower = q_raw.lower()
    if not q_raw:
        return False

    keywords = _get_keywords(rag_required_keywords)
    if _is_greeting_skip(q_raw, q_lower, keywords, trigger_threshold=trigger_threshold):
        return True
    _, _, triggered = compute_rag_trigger_score(
        question, rag_required_keywords=rag_required_keywords, trigger_threshold=trigger_threshold
    )
    return not triggered


__all__ = [
    "SKIP_RAG_GREETINGS",
    "SKIP_RAG_GREETING_MAX_LENGTH",
    "RAG_TRIGGER_THRESHOLD",
    "RAG_TRIGGER_PHRASES_STRONG",
    "RAG_TRIGGER_PHRASES_WEAK",
    "compute_rag_trigger_score",
    "should_skip_rag_search",
]
