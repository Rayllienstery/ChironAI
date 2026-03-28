"""
Tests for WebUI local markdown ingest payload helpers.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_WEBUI = _REPO / "WebUI"
for p in (_REPO, _WEBUI):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from ingest_markdown_common import (  # noqa: E402
    payloads_for_markdown,
    qdrant_payload_local,
)


class TestQdrantPayloadLocal:
    def test_keys_and_section_path_joined(self) -> None:
        p = qdrant_payload_local("docs/a.md", "body", ["One", "Two"])
        assert p["text"] == "body"
        assert p["source"] == "docs/a.md"
        assert p["path"] == "docs/a.md"
        assert p["section_path"] == ["One", "Two"]
        assert p["section_path_joined"] == "One:Two"

    def test_empty_section_path(self) -> None:
        p = qdrant_payload_local("x.md", "t", [])
        assert p["section_path"] == []
        assert p["section_path_joined"] == ""


class TestPayloadsForMarkdown:
    def test_fixture_has_expected_payload_shape(self) -> None:
        md = """# Title

First paragraph with enough words to pass quality check for chunking rules.

## Section

More text here also with sufficient words for the minimum chunk word count.
"""
        payloads = payloads_for_markdown(md, "sample.md")
        assert len(payloads) >= 1
        for pl in payloads:
            assert "text" in pl and pl["text"].strip()
            assert pl["source"] == "sample.md"
            assert pl["path"] == "sample.md"
            assert "section_path" in pl
            assert "section_path_joined" in pl
            assert isinstance(pl["section_path"], list)
