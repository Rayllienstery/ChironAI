from __future__ import annotations

import os
import sys

import pytest


# Ensure external_docs_rag package is importable.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_EXT_RAG_ROOT = os.path.join(_ROOT, "modules", "external_docs_rag")
if _EXT_RAG_ROOT not in sys.path:
    sys.path.insert(0, _EXT_RAG_ROOT)


from external_docs_rag.application.use_cases import build_merged_rag_context, fetch_on_demand_context
from external_docs_rag.domain.entities import ExternalSource, RagSourceConfig


class MockDoc:
    def __init__(
        self,
        url: str,
        content: str,
        source_id: str,
        filename: str,
        content_type: str = "text/markdown",
    ) -> None:
        self.url = url
        self.content = content
        self.source_id = source_id
        self.filename = filename
        self.content_type = content_type


class MockFetchClient:
    def __init__(self, content: str = "ignored") -> None:
        self._content = content

    def fetch(self, url: str):
        return MockDoc(
            url=url,
            content=self._content,
            source_id="mock-source",
            filename="README.md",
            content_type="text/markdown",
        )


class MockEmbed:
    def embed(self, text: str):
        return [0.0] * 64


class MockRagSearchPort:
    def search(self, collection_name: str, vec, top_k: int):
        raise AssertionError("RAG search should not be called for on_demand_fetch sources")


def _expected_preview(full: str, limit: int = 100) -> str:
    if len(full) <= limit:
        return full
    return full[:limit] + "..."


def test_fetch_on_demand_context_includes_text_length_and_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    import external_docs_rag.application.use_cases as uc

    # fetch_on_demand_context checks md.strip() length, so return a sufficiently long string.
    monkeypatch.setattr(uc, "parse_document_to_markdown", lambda doc: "X" * 60)
    monkeypatch.setattr(
        uc,
        "split_markdown_into_chunks",
        lambda md: [
            ("A" * 122, "SectionA"),
            ("B" * 50, "SectionB"),
        ],
    )
    monkeypatch.setattr(uc, "chunk_quality_ok", lambda chunk: True)

    source = ExternalSource(
        id="mock-framework",
        base_url="https://example.com",
        paths=["docs/readme.md"],
        collection_name="MockCollection",
    )

    ctx_text, chunks_info = fetch_on_demand_context(
        source=source,
        fetch_client=MockFetchClient(),
        context_max_chars=10_000,
        question=None,
        ref_override=None,
    )

    assert isinstance(ctx_text, str)
    assert len(chunks_info) == 2

    chunk1 = "A" * 122
    chunk2 = "B" * 50

    assert chunks_info[0]["text_length"] == len(chunk1)
    assert chunks_info[0]["text_preview"] == _expected_preview(chunk1)

    assert chunks_info[1]["text_length"] == len(chunk2)
    assert chunks_info[1]["text_preview"] == _expected_preview(chunk2)


def test_build_merged_rag_context_propagates_on_demand_chunk_sizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import external_docs_rag.application.use_cases as uc

    monkeypatch.setattr(uc, "parse_document_to_markdown", lambda doc: "X" * 60)
    monkeypatch.setattr(
        uc,
        "split_markdown_into_chunks",
        lambda md: [
            ("A" * 122, "SectionA"),
            ("B" * 50, "SectionB"),
        ],
    )
    monkeypatch.setattr(uc, "chunk_quality_ok", lambda chunk: True)
    monkeypatch.setattr(uc, "extract_candidate_framework_names", lambda _q: [])

    source = ExternalSource(
        id="mock-framework",
        base_url="https://example.com",
        paths=["docs/readme.md"],
        collection_name="MockCollection",
    )

    cfg = RagSourceConfig(
        collection_name="mock-collection",
        top_k=2,
        trigger_keywords=[],
        label="MockCollectionLabel",
        on_demand_fetch=True,
        external_source_id=source.id,
    )

    ctx, _timings = build_merged_rag_context(
        question="What is SwiftUI?",
        rag_sources=[cfg],
        rag_search=MockRagSearchPort(),
        embed_provider=MockEmbed(),
        context_chunk_chars=500,
        context_total_chars=10_000,
        fetch_client=MockFetchClient(),
        external_sources=[source],
        fresh_collection_names=None,
    )

    assert ctx.chunks_info, "Expected on-demand chunks in merged RAG context"
    for c in ctx.chunks_info:
        assert "text_length" in c
        assert "text_preview" in c
        assert isinstance(c["text_length"], int)
        assert isinstance(c["text_preview"], str)

