"""
Offline linter for RAG tests.

Scans all Markdown-defined tests under rag_tests/ and flags Expected Concepts
entries that look like combined concepts (e.g. "weak / unowned").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List

from application.rag_tests.loader import load_all_tests, get_rag_tests_root


MULTI_CONCEPT_SEPARATORS: tuple[str, ...] = ("/", ",", ";", " and ")


@dataclass
class ConceptLintIssue:
    """Represents a single problematic Expected Concept entry."""

    test_id: str
    file_path: str
    concept: str
    message: str


def _looks_multi_concept(concept: str) -> bool:
    """Heuristic: entry probably contains multiple concepts."""
    text = (concept or "").strip()
    if not text:
        return False
    lowered = text.lower()
    # Obvious separators that usually indicate a list of things.
    if any(sep in lowered for sep in MULTI_CONCEPT_SEPARATORS):
        return True
    # Very long concept with multiple spaces is unlikely to be a single atomic term.
    if len(text) > 60 and " " in text:
        return True
    return False


def lint_expected_concepts(tests: Iterable[dict[str, Any]] | None = None) -> List[ConceptLintIssue]:
    """
    Lint all tests (or provided subset) for multi-concept Expected Concepts.

    Returns a list of ConceptLintIssue objects.
    """
    if tests is None:
        root = get_rag_tests_root()
        tests = load_all_tests(root)

    issues: List[ConceptLintIssue] = []
    for t in tests:
        concepts = t.get("expected_concepts") or []
        file_path = t.get("file_path") or t.get("absolute_path") or t.get("id") or "unknown"
        test_id = t.get("id") or file_path
        for c in concepts:
            if _looks_multi_concept(c):
                msg = "Expected Concepts entry looks like multiple concepts; split into separate bullets."
                issues.append(
                    ConceptLintIssue(
                        test_id=test_id,
                        file_path=file_path,
                        concept=c,
                        message=msg,
                    )
                )
    return issues


def format_issues_text(issues: Iterable[ConceptLintIssue]) -> str:
    """Human-readable text representation for CLI / logs."""
    out_lines: list[str] = []
    issues_list = list(issues)
    if not issues_list:
        return "No multi-concept Expected Concepts entries found."
    out_lines.append(f"Found {len(issues_list)} potential multi-concept Expected Concepts entries:\n")
    for issue in issues_list:
        out_lines.append(
            f"- [{issue.test_id}] ({issue.file_path}) \"{issue.concept}\": {issue.message}"
        )
    return "\n".join(out_lines)


__all__ = ["ConceptLintIssue", "lint_expected_concepts", "_looks_multi_concept", "format_issues_text"]

