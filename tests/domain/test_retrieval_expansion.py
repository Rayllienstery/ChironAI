"""Tests for query expansion and RRF merge helpers."""

from __future__ import annotations

from unittest.mock import patch

from domain.services.retrieval import expand_query_variants, rrf_merge_hit_lists


def test_rrf_merge_dedupes_by_id() -> None:
    a = [{"id": 1, "score": 1.0, "payload": {"text": "x"}}]
    b = [{"id": 1, "score": 0.5, "payload": {"text": "x"}}]
    out = rrf_merge_hit_lists([a, b], limit=5)
    assert len(out) == 1
    assert out[0]["id"] == 1


def test_expand_query_variants_disabled_returns_single() -> None:
    with patch("domain.services.retrieval.get_retrieval_bool", return_value=False):
        v = expand_query_variants("How does MVVM work in SwiftUI?")
        assert v == ["How does MVVM work in SwiftUI?"]


def test_expand_query_variants_adds_phrase_when_enabled() -> None:
    with patch("domain.services.retrieval.get_retrieval_bool", return_value=True):
        with patch("domain.services.retrieval.get_retrieval_int", return_value=3):
            with patch(
                "domain.services.retrieval.get_retrieval_dict",
                return_value={"MVVM": "Model View ViewModel"},
            ):
                v = expand_query_variants("How does MVVM work in SwiftUI?")
                assert len(v) >= 2
                assert any("Model View ViewModel" in x for x in v)
