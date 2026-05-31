"""
Unit tests for rag_service.domain.services.metadata_inference.
"""

from __future__ import annotations


from rag_service.domain.services.metadata_inference import extract_versions, infer_metadata


class TestExtractVersions:
    def test_extracts_ios_version(self) -> None:
        ios, swift = extract_versions("Available in iOS 18+")
        assert "18" in ios
        assert swift == []

    def test_extracts_swift_version(self) -> None:
        ios, swift = extract_versions("Swift 5.10 concurrency")
        assert "5.10" in swift
        assert ios == []

    def test_returns_sorted_unique(self) -> None:
        ios, swift = extract_versions("iOS 18 and iOS 18 again")
        assert ios == ["18"]


class TestInferMetadata:
    def test_apple_documentation_swift(self) -> None:
        meta = infer_metadata(
            "apple_documentation",
            "view.md",
            "https://developer.apple.com/documentation/swiftui/view",
            ["View"],
            "text",
        )
        assert meta["language"] == "swift"
        assert meta["technology"] == "swiftui"

    def test_apple_documentation_uikit(self) -> None:
        meta = infer_metadata(
            "apple_documentation",
            "uiview.md",
            "https://developer.apple.com/documentation/uikit/uiview",
            [],
            "text",
        )
        assert meta["technology"] == "uikit"

    def test_unknown_source_defaults(self) -> None:
        meta = infer_metadata("unknown_src", "f.md", None, [], "text")
        assert meta["language"] == "unknown"
        assert meta["doc_type"] == "documentation"
