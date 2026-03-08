"""
Unit tests for domain.services.markdown_meta.
"""

from __future__ import annotations

import pytest

from domain.services.markdown_meta import parse_and_strip_meta_block


class TestParseAndStripMetaBlock:
    def test_empty_returns_unchanged(self) -> None:
        meta, rest = parse_and_strip_meta_block("")
        assert meta == {}
        assert rest == ""

    def test_no_comment_returns_unchanged(self) -> None:
        md = "# Title\n\nBody."
        meta, rest = parse_and_strip_meta_block(md)
        assert meta == {}
        assert rest == md

    def test_strips_comment_and_parses_meta(self) -> None:
        md = """<!--
meta:
  url: https://developer.apple.com/documentation/swiftui/view
  framework: SwiftUI
  doc_kind: conceptual
  availability:
    iOS: 17.0
    Swift: 5.9
-->
# View

Body text.
"""
        meta, rest = parse_and_strip_meta_block(md)
        assert meta.get("url") == "https://developer.apple.com/documentation/swiftui/view"
        assert meta.get("framework") == "SwiftUI"
        assert meta.get("doc_kind") == "conceptual"
        assert meta.get("availability") == {"iOS": "17.0", "Swift": "5.9"}
        assert meta.get("ios_versions") == ["17.0"]
        assert meta.get("swift_versions") == ["5.9"]
        assert rest.strip().startswith("# View")
        assert "Body text." in rest

    def test_no_availability_omits_version_lists(self) -> None:
        md = """<!--
meta:
  url: https://example.com
-->
# Title
"""
        meta, rest = parse_and_strip_meta_block(md)
        assert meta.get("url") == "https://example.com"
        assert "ios_versions" not in meta or meta.get("ios_versions") == []
        assert rest.strip().startswith("# Title")

    def test_parses_doc_scope(self) -> None:
        md = """<!--
meta:
  url: https://example.com/doc
  framework: SwiftUI
  doc_scope: api_symbol
-->
# Page
"""
        meta, rest = parse_and_strip_meta_block(md)
        assert meta.get("doc_scope") == "api_symbol"
        assert rest.strip().startswith("# Page")
