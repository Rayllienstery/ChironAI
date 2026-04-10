"""Unit tests for WWDC transcript helpers in crawler_service."""

from __future__ import annotations

from crawler_service.domain.wwdc_transcript import (
    extract_wwdc_session_id_from_url,
    flatten_wwdc_transcript_json,
    parse_wwdc_event_year,
)
from crawler_service.domain.url_rules import crawl_url_allowed, link_passes_filters


def test_parse_wwdc_event_year() -> None:
    assert parse_wwdc_event_year("WWDC24") == 2024
    assert parse_wwdc_event_year("WWDC2024") == 2024
    assert parse_wwdc_event_year("") is None


def test_extract_wwdc_session_id_from_url() -> None:
    y, sid = extract_wwdc_session_id_from_url(
        "https://example.com/wwdc2024/wwdc2024-10136-transcript-eng.json"
    )
    assert y == 2024
    assert sid == "10136"


def test_flatten_wwdc_transcript_json_time_text_pair() -> None:
    data = [[0.0, "Hello world"], [1.0, "Second line"]]
    segs = flatten_wwdc_transcript_json(data)
    assert len(segs) == 2
    assert segs[0]["text"] == "Hello world"


def test_crawl_url_allowed_documentation_path() -> None:
    from urllib.parse import urlparse

    start = urlparse("https://developer.apple.com/documentation/swift")
    visited: set[str] = set()
    ok = crawl_url_allowed(
        "https://developer.apple.com/documentation/swift/string",
        1,
        3,
        start,
        "https://developer.apple.com",
        "/documentation/swift",
        True,
        visited,
        path_roots=["/documentation/swift"],
        excluded_substrings=["/wwdc"],
    )
    assert ok is True


def test_link_passes_filters_rejects_wwdc_substring() -> None:
    from urllib.parse import urlparse

    start = urlparse("https://developer.apple.com/documentation/swift")
    ok = link_passes_filters(
        "https://developer.apple.com/documentation/swift/wwdc/foo",
        start,
        "/documentation/swift",
        True,
        path_roots=["/documentation/swift"],
        excluded_substrings=["/wwdc"],
    )
    assert ok is False
