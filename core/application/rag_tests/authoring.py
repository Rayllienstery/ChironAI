"""Authoring helpers for Markdown-defined RAG tests."""

from __future__ import annotations


def normalize_concepts(raw_concepts: list[str]) -> list[str]:
    """
    Normalize Expected Concepts coming from the WebUI/CLI.

    Rules:
    - One atomic concept per entry (no combined lists like `weak / unowned`).
    - Trim whitespace and drop empty entries.
    - Split on common separators (`/`, `,`, `;`, ` and `) when they clearly
      represent multiple concepts, for example:
        - "weak / unowned" -> ["weak", "unowned"]
        - "weak and unowned" -> ["weak", "unowned"]
    - If the string still looks ambiguous after splitting, keep it as-is so
      the author can fix it.
    """
    normalized: list[str] = []
    for item in raw_concepts:
        text = (item or "").strip()
        if not text:
            continue

        lowered = text.lower()
        if all(sep not in lowered for sep in ("/", ",", ";", " and ")):
            normalized.append(text)
            continue

        candidates: list[str] = []

        def _split_and_extend(separator: str) -> None:
            parts = [p.strip() for p in text.split(separator) if p.strip()]
            if len(parts) >= 2:
                candidates.extend(parts)

        if " and " in lowered:
            _split_and_extend(" and ")
        if "/" in text:
            _split_and_extend("/")
        if "," in text:
            _split_and_extend(",")
        if ";" in text:
            _split_and_extend(";")

        if len(candidates) >= 2 and all(len(c) <= 40 for c in candidates):
            for candidate in candidates:
                if candidate and candidate not in normalized:
                    normalized.append(candidate)
            continue

        normalized.append(text)

    return normalized


def build_rag_test_markdown(
    name: str,
    question: str,
    concepts: list[str],
    platform: str,
    framework: str,
    difficulty: str,
    concept_mode: str,
    rag_strict: bool,
    min_os: str,
    notes: str,
) -> str:
    """Build .md file content for create/update."""
    lines = [
        f"# {name}",
        "",
        f"Platform: {platform}",
        f"Framework: {framework}",
        f"Difficulty: {difficulty}",
        f"Concept Mode: {concept_mode}",
    ]
    if rag_strict:
        lines.append("RAG Strict: true")
    if min_os:
        lines.append(f"MinOS: {min_os}")
    lines.extend(["", "## Question", "", question, "", "## Expected Concepts", ""])
    for concept in concepts:
        lines.append(f"- {concept}")
    lines.extend(["", "## RAG Requirement", "", "The answer must reference retrieved documentation or RAG context.", ""])
    if notes:
        lines.extend(["## Notes", "", notes])
    return "\n".join(lines)
