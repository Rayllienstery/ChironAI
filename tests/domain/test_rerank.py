"""
Unit tests for rag_service.domain.services.rerank.
"""

from __future__ import annotations


from rag_service.domain.services.rerank import (
    apply_rerank_scores_and_cut,
    build_rerank_prompt,
    extract_candidates_from_rerank_prompt,
    parse_rerank_order,
    reorder_hits_by_indices,
    shorten_for_rerank,
    native_rerank_response_to_order,
)


class TestShortenForRerank:
    def test_returns_short_text_unchanged(self) -> None:
        assert shorten_for_rerank("hello", max_len=10) == "hello"

    def test_truncates_long_text_with_ellipsis(self) -> None:
        out = shorten_for_rerank("a" * 20, max_len=10)
        assert len(out) == 10
        assert out.endswith("\u2026")

    def test_empty_returns_empty(self) -> None:
        assert shorten_for_rerank("") == ""


class TestBuildRerankPrompt:
    def test_includes_question_and_numbered_chunks(self) -> None:
        prompt = build_rerank_prompt("Q?", [(1, "text1"), (2, "text2")])
        assert "Q?" in prompt
        assert "1:" in prompt
        assert "2:" in prompt
        assert "text1" in prompt
        assert "text2" in prompt

    def test_empty_candidates(self) -> None:
        prompt = build_rerank_prompt("Q?", [])
        assert "Q?" in prompt


class TestParseRerankOrder:
    def test_parses_json_array(self) -> None:
        order = parse_rerank_order("[2, 1, 3]")
        assert order == [2, 1, 3]

    def test_returns_none_for_invalid_json(self) -> None:
        assert parse_rerank_order("not json") is None

    def test_returns_none_for_empty(self) -> None:
        assert parse_rerank_order("") is None

    def test_returns_none_for_non_list(self) -> None:
        assert parse_rerank_order('{"a": 1}') is None


class TestExtractCandidatesFromRerankPrompt:
    def test_extracts_numbered_snippets(self) -> None:
        prompt = build_rerank_prompt("Q?", [(1, "text1"), (2, "text2")])
        out = extract_candidates_from_rerank_prompt(prompt)
        assert out == [(1, "text1"), (2, "text2")]

    def test_empty_prompt_returns_empty_list(self) -> None:
        assert extract_candidates_from_rerank_prompt("") == []


class TestNativeRerankResponseToOrder:
    def test_orders_documents_by_results_sequence(self) -> None:
        raw = {
            "results": [
                {"document": "IDX2: text2", "relevance_score": 0.9},
                {"document": "IDX1: text1", "relevance_score": 0.8},
            ]
        }
        out = native_rerank_response_to_order(raw)
        assert out == [2, 1]

    def test_deduplicates_indices(self) -> None:
        raw = {
            "results": [
                {"document": "IDX1: text1", "relevance_score": 0.9},
                {"document": "IDX1: text1", "relevance_score": 0.8},
                {"document": "IDX2: text2", "relevance_score": 0.7},
            ]
        }
        out = native_rerank_response_to_order(raw)
        assert out == [1, 2]

    def test_returns_none_on_invalid_shape(self) -> None:
        assert native_rerank_response_to_order({}) is None
        assert native_rerank_response_to_order({"results": "not-a-list"}) is None


class TestReorderHitsByIndices:
    def test_reorders_by_1based_indices(self) -> None:
        candidates = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        all_hits = list(candidates)
        out = reorder_hits_by_indices(candidates, [2, 1, 3], all_hits)
        assert out[0]["id"] == "b"
        assert out[1]["id"] == "a"
        assert out[2]["id"] == "c"

    def test_empty_candidates_returns_all_hits(self) -> None:
        all_hits = [{"id": "x"}]
        out = reorder_hits_by_indices([], [], all_hits)
        assert out == all_hits


class TestApplyRerankScoresAndCut:
    def test_adds_rerank_score_and_cuts(self) -> None:
        hits = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        out = apply_rerank_scores_and_cut(hits, final_k=2)
        assert len(out) == 2
        assert out[0]["rerank_score"] == 1.0
        assert out[1]["rerank_score"] == 0.5

    def test_empty_returns_empty(self) -> None:
        assert apply_rerank_scores_and_cut([], 5) == []
