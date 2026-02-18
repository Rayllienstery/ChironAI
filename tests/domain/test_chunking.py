"""
Unit tests for domain.services.chunking.
"""

from __future__ import annotations

import pytest

from domain.services.chunking import chunk_quality_ok, split_markdown_into_chunks


class TestChunkQualityOk:
    def test_false_for_empty(self) -> None:
        assert chunk_quality_ok("") is False

    def test_false_for_too_few_words(self) -> None:
        assert chunk_quality_ok("one two") is False

    def test_true_for_sufficient_words_and_alpha(self) -> None:
        text = "This is a valid chunk with enough words and letters."
        assert chunk_quality_ok(text) is True


class TestSplitMarkdownIntoChunks:
    def test_empty_returns_empty(self) -> None:
        assert split_markdown_into_chunks("") == []

    def test_splits_by_paragraphs(self) -> None:
        md = "Para 1.\n\nPara 2.\n\nPara 3."
        chunks = split_markdown_into_chunks(md, max_chunk_size=100, min_chunk_size=5)
        assert len(chunks) >= 1
        for text, path in chunks:
            assert isinstance(text, str)
            assert isinstance(path, list)

    def test_respects_headings(self) -> None:
        md = "# Title\n\nBody here.\n\n## Section\n\nMore body."
        chunks = split_markdown_into_chunks(md, max_chunk_size=200, min_chunk_size=5)
        assert len(chunks) >= 1
