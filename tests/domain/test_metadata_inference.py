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

    def test_doc_scope_from_discussion_section(self) -> None:
        meta = infer_metadata(
            "apple_documentation",
            "view.md",
            "https://developer.apple.com/documentation/swiftui/view",
            ["View", "Discussion"],
            "text",
        )
        assert meta["doc_scope"] == "api_symbol"

    def test_doc_scope_from_overview_section(self) -> None:
        meta = infer_metadata(
            "apple_documentation",
            "swiftui.md",
            "https://developer.apple.com/documentation/swiftui",
            ["SwiftUI", "Overview"],
            "text",
        )
        assert meta["doc_scope"] == "guide"

    def test_symbol_from_type_title(self) -> None:
        from rag_service.domain.services.metadata_inference import infer_chunk_display_meta

        display = infer_chunk_display_meta(["NavigationStack"])
        assert display.get("symbol") == "NavigationStack"

    def test_community_source_defaults_to_ios_guide(self) -> None:
        meta = infer_metadata(
            "hws_swift",
            "how-to-show-a-context-menu.md",
            "https://www.hackingwithswift.com/quick-start/swiftui/how-to-show-a-context-menu",
            ["How to show a context menu"],
            "SwiftUI gives us the ContextMenu modifier.",
        )
        assert meta["technology"] == "swiftui"
        assert meta["product"] == "ios"
        assert meta["doc_scope"] == "guide"

    def test_wwdc_infers_session_technology(self) -> None:
        meta = infer_metadata(
            "wwdc_sessions_2019_plus",
            "wwdc2024-10161.md",
            "https://developer.apple.com/videos/play/wwdc2024/10161/",
            ["Deploy machine learning and AI models on-device with Core ML"],
            "Core ML helps you optimize models for on-device machine learning.",
        )
        assert meta["technology"] == "core ml"
        assert meta["doc_scope"] == "session"

    def test_unknown_source_defaults(self) -> None:
        meta = infer_metadata("unknown_src", "f.md", None, [], "text")
        assert meta["language"] == "unknown"
        assert meta["doc_type"] == "documentation"
