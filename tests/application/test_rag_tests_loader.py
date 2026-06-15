"""
Unit tests for application.rag_tests.loader.
"""

from __future__ import annotations

from pathlib import Path

from application.rag_tests.loader import (
    get_rag_tests_root,
    list_test_filters,
    load_all_tests,
    load_test,
    parse_test_md,
)


class TestParseTestMd:
    """Tests for parse_test_md."""

    def test_parse_full_document_returns_all_fields(self) -> None:
        content = """
# Observation with UIKit

Platform: iOS
Framework: SwiftUI
MinOS: iOS 18
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

Tell me about @Observation with UIKit.

## Expected Concepts

- updateProperties()
- viewWillLayoutSubviews()

## RAG Requirement

The answer must reference RAG context.

## Notes

Verifies Observation + UIKit.
"""
        out = parse_test_md(content)
        assert out["name"] == "Observation with UIKit"
        assert out["platform"] == "iOS"
        assert out["framework"] == "SwiftUI"
        assert out["min_os"] == "iOS 18"
        assert out["difficulty"] == "intermediate"
        assert out["concept_mode"] == "all"
        assert out["rag_strict"] is True
        assert "Tell me about @Observation" in out["question"]
        assert out["expected_concepts"] == ["updateProperties()", "viewWillLayoutSubviews()"]
        assert out["rag_requirement"] is True
        assert "Verifies Observation" in out["notes"]

    def test_parse_minimal_document_only_question(self) -> None:
        content = """
# Minimal

Platform: iOS

## Question

What is SwiftUI?
"""
        out = parse_test_md(content)
        assert out["name"] == "Minimal"
        assert out["question"] == "What is SwiftUI?"
        assert out["expected_concepts"] == []
        assert out["concept_mode"] == "all"
        assert out["rag_strict"] is False

    def test_parse_empty_returns_defaults(self) -> None:
        out = parse_test_md("")
        assert out["name"] == ""
        assert out["question"] == ""
        assert out["expected_concepts"] == []
        assert out["difficulty"] == "intermediate"
        assert out["concept_mode"] == "all"
        assert out["rag_strict"] is False

    def test_parse_concept_mode_any(self) -> None:
        content = """
# Any

Platform: iOS
Concept Mode: any

## Question

Q?

## Expected Concepts

- A
- B
"""
        out = parse_test_md(content)
        assert out["concept_mode"] == "any"

    def test_parse_rag_strict_yes_and_one(self) -> None:
        for value in ("yes", "true", "1"):
            content = f"""
# Test
Platform: iOS
RAG Strict: {value}

## Question
Q?
"""
            out = parse_test_md(content)
            assert out["rag_strict"] is True, value

    def test_parse_rag_strict_false_when_empty_or_no(self) -> None:
        content = """
# Test
Platform: iOS
RAG Strict: false

## Question
Q?
"""
        out = parse_test_md(content)
        assert out["rag_strict"] is False


class TestLoadTest:
    """Tests for load_test with temp directory."""

    def test_load_test_returns_dict_with_id_and_question(self, tmp_path: Path) -> None:
        md = tmp_path / "one.md"
        md.write_text("""
# One Test
Platform: iOS
Framework: SwiftUI

## Question
What is Swift?

## Expected Concepts
- swift
""", encoding="utf-8")
        result = load_test(tmp_path, md)
        assert result is not None
        assert result["name"] == "One Test"
        assert result["question"] == "What is Swift?"
        assert "id" in result
        assert "file_path" in result
        assert result["expected_concepts"] == ["swift"]

    def test_load_test_returns_none_for_non_md(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").write_text("hello")
        assert load_test(tmp_path, tmp_path / "readme.txt") is None


class TestLoadAllTestsAndFilters:
    """Tests for load_all_tests and list_test_filters."""

    def test_load_all_tests_and_filters_from_temp_dir(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("""
# A
Platform: iOS
Framework: SwiftUI
Difficulty: beginner

## Question
Q1?
""", encoding="utf-8")
        (tmp_path / "b.md").write_text("""
# B
Platform: iOS
Framework: UIKit
Difficulty: advanced

## Question
Q2?
""", encoding="utf-8")
        tests = load_all_tests(tmp_path)
        assert len(tests) == 2
        names = {t["name"] for t in tests}
        assert names == {"A", "B"}
        filters = list_test_filters(tests)
        assert filters["platform"] == ["iOS"]
        assert set(filters["framework"]) == {"SwiftUI", "UIKit"}
        assert set(filters["difficulty"]) == {"advanced", "beginner"}


class TestGetRagTestsRoot:
    """Tests for get_rag_tests_root."""

    def test_returns_path_containing_rag_tests(self) -> None:
        root = get_rag_tests_root()
        assert root is not None
        assert root.name == "rag_tests" or "rag_tests" in str(root)
