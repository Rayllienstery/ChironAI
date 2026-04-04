"""
Unit tests for domain.services.chunking.
"""

from __future__ import annotations

import pytest

from domain.services.chunking import (
    chunk_quality_ok,
    split_markdown_into_chunks,
    _is_heading_only_chunk,
)


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

    def test_code_block_with_internal_blank_line_stays_one_unit(self) -> None:
        md = "# API\n\nText.\n\n```swift\nfunc foo() {\n\n}\n```\n\nAfter."
        chunks = split_markdown_into_chunks(md, max_chunk_size=500, min_chunk_size=5)
        assert len(chunks) >= 1
        texts = [t for t, _ in chunks]
        combined = "\n\n".join(texts)
        assert "```swift" in combined
        assert "func foo()" in combined
        assert "After." in combined

    def test_long_paragraph_splits_by_sentence(self) -> None:
        long_para = "First sentence here. Second sentence there. Third one. " * 50
        chunks = split_markdown_into_chunks(
            long_para, max_chunk_size=200, min_chunk_size=10, chunk_overlap=0
        )
        assert len(chunks) >= 2
        for text, path in chunks:
            assert len(text) <= 250
            assert isinstance(path, list)

    def test_overlap_produces_multiple_chunks(self) -> None:
        md = "# A\n\n" + "Word. " * 80 + "\n\n" + "Other. " * 80
        chunks_no_overlap = split_markdown_into_chunks(
            md, max_chunk_size=150, min_chunk_size=20, chunk_overlap=0
        )
        chunks_with_overlap = split_markdown_into_chunks(
            md, max_chunk_size=150, min_chunk_size=20, chunk_overlap=30
        )
        assert len(chunks_no_overlap) >= 1
        assert len(chunks_with_overlap) >= 2
        for text, path in chunks_with_overlap:
            assert isinstance(text, str) and len(text) >= 1
            assert path == [] or path == ["A"]

    def test_section_path_preserved_after_merge(self) -> None:
        md = "## Section One\n\nShort.\n\n## Section One\n\nAlso short."
        chunks = split_markdown_into_chunks(
            md, max_chunk_size=500, min_chunk_size=5, chunk_overlap=0
        )
        assert len(chunks) >= 1
        for _text, path in chunks:
            assert isinstance(path, list)
            assert path == ["Section One"] or "Section One" in path

    def test_heading_only_chunk_merged_with_next_same_section(self) -> None:
        # When section path is the same, heading-only chunk merges with next (e.g. "## Parameters" + body).
        # Use small max so we flush after "## Parameters" and get a heading-only chunk then body chunk.
        long_body = "transform: (Value) throws -> T. " * 80
        md = "# mapValues(_:)\n\n## Parameters\n\n" + long_body
        chunks = split_markdown_into_chunks(
            md, max_chunk_size=100, min_chunk_size=10, chunk_overlap=0
        )
        # No chunk should be only "## Parameters" with no body (merge pass should combine them).
        for text, path in chunks:
            if path == ["mapValues(_:)", "Parameters"] and text.strip() == "## Parameters":
                pytest.fail("Parameters chunk must include body after merge")
        combined = "\n\n".join(t for t, _ in chunks)
        assert "## Parameters" in combined
        assert "transform:" in combined

    def test_heading_only_merge_same_section_path(self) -> None:
        md = "## Parameters\n\nOne param here."
        chunks = split_markdown_into_chunks(
            md, max_chunk_size=500, min_chunk_size=5, chunk_overlap=0
        )
        assert len(chunks) == 1
        text, path = chunks[0]
        assert "## Parameters" in text
        assert "One param here." in text
        assert path == ["Parameters"]


class TestIsHeadingOnlyChunk:
    def test_true_for_single_heading(self) -> None:
        assert _is_heading_only_chunk("# Title") is True
        assert _is_heading_only_chunk("## Parameters") is True

    def test_true_for_multiple_headings_only(self) -> None:
        assert _is_heading_only_chunk("## A\n\n### B") is True

    def test_false_for_heading_plus_content(self) -> None:
        assert _is_heading_only_chunk("## Parameters\n\nBody text.") is False
        assert _is_heading_only_chunk("Some text.") is False

    def test_false_for_empty(self) -> None:
        assert _is_heading_only_chunk("") is False
