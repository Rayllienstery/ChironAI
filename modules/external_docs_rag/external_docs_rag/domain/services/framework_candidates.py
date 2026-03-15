"""
Extract candidate framework/library names from a question for generic doc discovery.
"""

from __future__ import annotations

import re

# Words we skip: too generic or not framework names.
STOPWORDS = frozenset({
    "swift", "ios", "apple", "xcode", "macos", "watchos", "tvos", "ipad", "iphone",
    "android", "linux", "windows", "github", "git", "cocoapods", "spm", "carthage",
    "swiftui", "uikit", "appkit", "combine", "foundation", "core", "data",
    "the", "and", "for", "with", "how", "what", "when", "why", "using", "use",
})

# Max candidates to try for discovery (avoid rate limits and latency).
MAX_CANDIDATES = 3

# Min length for a candidate (avoid "UI", "ID").
MIN_CANDIDATE_LEN = 3


def extract_candidate_framework_names(question: str) -> list[str]:
    """
    Extract tokens that look like framework/library names (CamelCase or known patterns).
    Returns a deduplicated list, up to MAX_CANDIDATES, for generic doc discovery.
    """
    if not question or not question.strip():
        return []
    text = question.strip()
    seen: set[str] = set()
    out: list[str] = []

    # CamelCase: one or more segments starting with uppercase (e.g. Alamofire, SnapKit, RxSwift).
    for m in re.finditer(r"\b([A-Z][a-z0-9]*(?:[A-Z][a-z0-9]*)+)\b", text):
        name = m.group(1)
        if len(name) < MIN_CANDIDATE_LEN:
            continue
        key = name.lower()
        if key in STOPWORDS or key in seen:
            continue
        seen.add(key)
        out.append(name)
        if len(out) >= MAX_CANDIDATES:
            break

    # Single capitalized word that might be a framework (e.g. Kingfisher, Lottie).
    if len(out) < MAX_CANDIDATES:
        for m in re.finditer(r"\b([A-Z][a-z][a-zA-Z0-9]{2,})\b", text):
            name = m.group(1)
            key = name.lower()
            if key in STOPWORDS or key in seen:
                continue
            seen.add(key)
            out.append(name)
            if len(out) >= MAX_CANDIDATES:
                break

    return out[:MAX_CANDIDATES]


# Version pattern: x.y or x.y.z, optional leading "v"
VERSION_RE = re.compile(
    r"(?:^|\s)(?:v)?(\d+\.\d+(?:\.\d+)?)(?:\s|$|[,\)\.])",
    re.IGNORECASE,
)
# "версии 5.8", "version 5.8", "версия 5.11.1"
VERSION_AFTER_WORD_RE = re.compile(
    r"(?:версии?|version|release)\s*[:\s]*(\d+\.\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def extract_framework_version_pairs(question: str) -> list[tuple[str, str | None]]:
    """
    Extract (framework_name, version) from the question.
    Version can be explicit (e.g. "Alamofire 5.8", "версии 5.11.1") or None if not mentioned.
    Returns list of (name, version_str or None) for each candidate framework found.
    """
    if not question or not question.strip():
        return []
    text = question.strip()
    candidates = extract_candidate_framework_names(question)
    if not candidates:
        return []

    # Global version mention (e.g. "последняя версия ... 5.11.1" or "version 5.8")
    global_version: str | None = None
    for m in VERSION_AFTER_WORD_RE.finditer(text):
        global_version = m.group(1)
        break
    if not global_version:
        for m in VERSION_RE.finditer(text):
            global_version = m.group(1)
            break

    out: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for name in candidates:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        # Look for version near this name: "Alamofire 5.8", "5.8 Alamofire", "Alamofire v5.8.0"
        version_near: str | None = None
        pos = text.find(name)
        if pos >= 0:
            before = text[max(0, pos - 40) : pos]
            after = text[pos + len(name) : pos + len(name) + 40]
            for m in VERSION_RE.finditer(" " + before + " "):
                version_near = m.group(1)
                break
            if not version_near:
                for m in VERSION_RE.finditer(" " + after + " "):
                    version_near = m.group(1)
                    break
        out.append((name, version_near or global_version))
    return out


__all__ = [
    "extract_candidate_framework_names",
    "extract_framework_version_pairs",
    "MAX_CANDIDATES",
]
