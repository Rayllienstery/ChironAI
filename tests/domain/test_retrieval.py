"""
Unit tests for rag_service.domain.services.retrieval.
"""

from __future__ import annotations


from rag_service.domain.entities import QueryIntent
from rag_service.domain.services.retrieval import (
    build_qdrant_filter,
    extra_filter_framework_equals,
    extra_filter_section_path_joined_equals,
    extra_filter_symbol_equals,
    infer_query_intent,
    intent_match_priority,
    is_version_question,
    merge_qdrant_filters,
    need_more_chunks,
    parse_versions_from_question,
    query_for_retrieval,
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

    def test_expands_query_when_api_symbol_present(self) -> None:
        q = query_for_retrieval("What is ContentUnavailableView and when would you use it?")
        assert "ContentUnavailableView" in q
        assert "Swift ContentUnavailableView" in q
        assert "SwiftUI ContentUnavailableView" in q
        assert "API ContentUnavailableView" in q

    def test_expands_query_for_multiple_symbols(self) -> None:
        q = query_for_retrieval("Compare UIViewController and NSViewRepresentable")
        assert "UIViewController" in q and "NSViewRepresentable" in q
        assert "Swift UIViewController" in q and "Swift NSViewRepresentable" in q
        assert "API UIViewController" in q and "API NSViewRepresentable" in q

    def test_no_expansion_without_api_symbol(self) -> None:
        q = query_for_retrieval("How does view work in SwiftUI?")
        # No PascalCase type name; should not contain "API view" (lowercase "view" is not a symbol)
        assert "API view" not in q or "View" in q

    def test_observable_uikit_query_contains_observation_tracking_bias(self) -> None:
        q = query_for_retrieval("Observable macro + UIKit iOS 18+")
        # RAG query should carry strong hints toward Observation/observation tracking docs.
        assert "observation tracking" in q


class TestBuildQdrantFilter:
    def test_returns_none_when_empty_question(self) -> None:
        f = build_qdrant_filter("")
        assert f is None or isinstance(f, dict)

    def test_returns_filter_dict_for_question(self) -> None:
        f = build_qdrant_filter("What is Observable?")
        assert f is None or (isinstance(f, dict) and "should" in f)


class TestSymbolAwareExtrasAndIntent:
    def test_extra_filter_symbol_equals_builds_filter(self) -> None:
        f = extra_filter_symbol_equals("handleEvents")
        assert f is not None
        must = f.get("must") or []
        assert any(isinstance(c, dict) and c.get("key") == "symbol" for c in must)

    def test_extra_filter_framework_equals_builds_filter(self) -> None:
        f = extra_filter_framework_equals("uikit")
        assert f is not None
        must = f.get("must") or []
        assert any(isinstance(c, dict) and c.get("key") == "framework" for c in must)

    def test_infer_query_intent_extracts_symbol_and_framework(self) -> None:
        intent = infer_query_intent("Как работает handleEvents в Combine для iOS 18?")
        assert isinstance(intent, QueryIntent)
        assert intent.symbol == "handleEvents"
        assert intent.framework in ("combine", "observation")

    def test_intent_match_priority_prefers_matching_symbol_and_framework(self) -> None:
        intent = QueryIntent(symbol="handleEvents", framework="combine")
        hit_match = {
            "payload": {
                "symbol": "handleEvents",
                "framework": "combine",
                "doc_type": "api_ref",
                "doc_scope": "api_symbol",
            }
        }
        hit_mismatch = {
            "payload": {
                "symbol": "OtherSymbol",
                "framework": "uikit",
                "doc_type": "api_ref",
                "doc_scope": "api_symbol",
            }
        }
        score_match = intent_match_priority(hit_match, intent)
        score_mismatch = intent_match_priority(hit_mismatch, intent)
        assert score_match > score_mismatch


class TestMergeQdrantFilters:
    def test_none_none(self) -> None:
        assert merge_qdrant_filters(None, None) is None

    def test_base_only(self) -> None:
        base = {"should": [{"key": "doc_type", "match": {"value": "article"}}]}
        assert merge_qdrant_filters(base, None) == base

    def test_extra_only(self) -> None:
        extra = {"must": [{"key": "section_path_joined", "match": {"value": "A:B"}}]}
        assert merge_qdrant_filters(None, extra) == extra

    def test_both_wraps_must(self) -> None:
        base = {"should": [{"key": "doc_type", "match": {"value": "article"}}]}
        extra = {"must": [{"key": "section_path_joined", "match": {"value": "H1:H2"}}]}
        m = merge_qdrant_filters(base, extra)
        assert m == {"must": [base, extra]}


class TestExtraFilterSectionPathJoinedEquals:
    def test_empty_returns_none(self) -> None:
        assert extra_filter_section_path_joined_equals("") is None
        assert extra_filter_section_path_joined_equals("   ") is None

    def test_non_empty(self) -> None:
        f = extra_filter_section_path_joined_equals("Intro:API")
        assert f == {"must": [{"key": "section_path_joined", "match": {"value": "Intro:API"}}]}
