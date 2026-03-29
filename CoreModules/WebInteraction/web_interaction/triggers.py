"""When to attach a free web supplement to the RAG system prompt."""

from __future__ import annotations

import re
from typing import Literal

# Freshness / release intent (subset aligned with product TODO)
_FRESHNESS_PHRASES_EN = (
    "latest",
    "current version",
    "newest",
    "when was",
    "when did",
    "release date",
    "released",
)
_FRESHNESS_PHRASES_RU = (
    "последняя версия",
    "актуальн",
    "когда вышла",
    "когда вышел",
    "дата выхода",
    "релиз",
)

# iOS 9 … iOS 26+ (1–3 digits); matches "iOS 26", "iOS 18.2" prefix handled elsewhere
_IOS_VERSION_RE = re.compile(r"\bios\s*\d{1,3}\b", re.IGNORECASE)

# Framework / library names (extend as needed)
_FRAMEWORK_TOKENS = frozenset(
    {
        "swiftui",
        "uikit",
        "appkit",
        "watchkit",
        "combine",
        "asyncawait",
        "async/await",
        "@observable",
        "alamofire",
        "kingfisher",
        "swiftdata",
        "coredata",
        "tca",
        "the composable architecture",
        "composable architecture",
        "pointfree",
        "rxswift",
    }
)


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def wants_freshness_or_release(user_message: str) -> bool:
    q = _norm(user_message)
    if not q:
        return False
    if _IOS_VERSION_RE.search(user_message or ""):
        return True
    # Standalone "current" (TODO: freshness keywords) — not "currently"
    if re.search(r"\bcurrent\b", user_message or "", re.IGNORECASE):
        return True
    for p in _FRESHNESS_PHRASES_EN:
        if p in q:
            return True
    for p in _FRESHNESS_PHRASES_RU:
        if p in q:
            return True
    return False


def looks_like_framework_question(user_message: str) -> bool:
    q = _norm(user_message)
    if not q:
        return False
    for tok in _FRAMEWORK_TOKENS:
        if tok in q:
            return True
    return False


WebSupplementTrigger = Literal["none", "keywords", "low_confidence_framework"]


def decide_trigger(
    user_message: str,
    *,
    on_keywords: bool,
    on_low_confidence_framework: bool,
    max_score: float,
    confidence_threshold: float,
) -> WebSupplementTrigger:
    """
    Decide why we would fetch web snippets (caller still checks master enabled flag).
    """
    if on_keywords and wants_freshness_or_release(user_message):
        return "keywords"
    if (
        on_low_confidence_framework
        and looks_like_framework_question(user_message)
        and max_score < confidence_threshold
    ):
        return "low_confidence_framework"
    return "none"
