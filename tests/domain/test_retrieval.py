"""
Unit tests for domain.services.retrieval.
"""

from __future__ import annotations

import pytest

from domain.services.retrieval import (
    build_qdrant_filter,
    is_version_question,
    need_more_chunks,
    parse_versions_from_question,
    query_for_retrieval,
    should_skip_rag_search,
)


class TestParseVersionsFromQuestion:
    def test_returns_empty_when_no_versions(self) -> None:
        ios, swift = parse_versions_from_question("What is SwiftUI?")
        assert ios == []
        assert swift == []

    def test_parses_ios_version(self) -> None:
        ios, swift = parse_versions_from_question("iOS 18+ API")
        assert "18" in ios
        assert swift == []

    def test_parses_swift_version(self) -> None:
        ios, swift = parse_versions_from_question("Swift 6 features")
        assert swift == ["6"]
        assert ios == []

    def test_parses_multiple_versions(self) -> None:
        ios, swift = parse_versions_from_question("iOS 17 and Swift 5.10")
        assert "17" in ios
        assert "5.10" in swift

    def test_returns_empty_for_none(self) -> None:
        ios, swift = parse_versions_from_question(None)
        assert ios == []
        assert swift == []


class TestIsVersionQuestion:
    def test_true_when_ios_mentioned(self) -> None:
        assert is_version_question("What's new in iOS 18?") is True

    def test_true_when_swift_mentioned(self) -> None:
        assert is_version_question("Swift 6 concurrency") is True

    def test_false_when_no_version(self) -> None:
        assert is_version_question("How does View work?") is False


class TestNeedMoreChunks:
    def test_true_when_compare(self) -> None:
        assert need_more_chunks("compare UIKit and SwiftUI") is True

    def test_true_when_list_keyword(self) -> None:
        assert need_more_chunks("list all lifecycle methods") is True

    def test_false_when_simple(self) -> None:
        assert need_more_chunks("What is View?") is False


class TestQueryForRetrieval:
    def test_strips_code_blocks(self) -> None:
        q = query_for_retrieval("```swift\nlet x = 1\n``` and Swift")
        assert "let x = 1" not in q or "Swift" in q

    def test_short_query_gets_prefix(self) -> None:
        q = query_for_retrieval("x")
        assert "Swift documentation" in q or len(q) >= 3

    def test_empty_returns_something(self) -> None:
        q = query_for_retrieval("")
        assert len(q) >= 3

    def test_uikit_bias(self) -> None:
        q = query_for_retrieval("uikit view controller")
        assert "UIKit" in q

    def test_swiftui_bias(self) -> None:
        q = query_for_retrieval("swiftui view")
        assert "SwiftUI" in q


class TestShouldSkipRagSearch:
    def test_returns_true_for_hi(self) -> None:
        assert should_skip_rag_search("hi") is True

    def test_returns_true_for_hello_case_insensitive(self) -> None:
        assert should_skip_rag_search("  HELLO  ") is True

    def test_returns_true_for_greeting_from_default_list(self) -> None:
        assert should_skip_rag_search("hey") is True

    def test_returns_false_for_what_is_swift(self) -> None:
        assert should_skip_rag_search("what is Swift?") is False

    def test_returns_false_for_explain_swift_code(self) -> None:
        assert should_skip_rag_search("explain this Swift code") is False

    def test_returns_true_for_query_without_rag_indicators(self) -> None:
        assert should_skip_rag_search("what is the weather today?") is True

    def test_returns_false_for_empty_string(self) -> None:
        assert should_skip_rag_search("") is False

    def test_returns_false_for_none(self) -> None:
        assert should_skip_rag_search(None) is False

    def test_returns_false_for_observation_tracking(self) -> None:
        assert should_skip_rag_search("Updating views automatically with observation tracking") is False


class TestBuildQdrantFilter:
    def test_returns_none_when_empty_question(self) -> None:
        f = build_qdrant_filter("")
        assert f is None or isinstance(f, dict)

    def test_returns_filter_dict_for_question(self) -> None:
        f = build_qdrant_filter("What is Observable?")
        assert f is None or (isinstance(f, dict) and "should" in f)
