"""
Helpers to reorder markdown chunks when the user asks for version/requirements.
Puts Requirements and Installation sections first so the model sees current info.
"""

from __future__ import annotations


def wants_version_or_requirements(question: str | None) -> bool:
    """True if the question asks for version or requirements (any language)."""
    if not question or not (question or "").strip():
        return False
    q = (question or "").lower().strip()
    return (
        "version" in q
        or "requirements" in q
        or "requirement" in q
        or "последняя версия" in q
        or "требования" in q
        or "версия" in q
    )


def reorder_chunks_for_version_question(
    raw_chunks: list[tuple[str, list[str]]],
) -> list[tuple[str, list[str]]]:
    """Put Requirements and Installation sections first when user asks for version/requirements."""
    priority_keywords = ("requirements", "installation", "install")
    prioritized: list[tuple[str, list[str]]] = []
    rest: list[tuple[str, list[str]]] = []
    for chunk_text, section_path in raw_chunks:
        section_names = " ".join(section_path).lower()
        if any(kw in section_names for kw in priority_keywords):
            prioritized.append((chunk_text, section_path))
        else:
            rest.append((chunk_text, section_path))
    return prioritized + rest


__all__ = ["wants_version_or_requirements", "reorder_chunks_for_version_question"]
