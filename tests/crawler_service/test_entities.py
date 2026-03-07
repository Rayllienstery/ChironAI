"""Tests for crawler_service.domain.entities."""

import pytest

from crawler_service.domain.entities import CrawlSource, crawl_source_from_dict


def test_crawl_source_from_dict() -> None:
    d = {"id": "apple_docs", "url": "https://developer.apple.com", "max_depth": 3}
    src = crawl_source_from_dict(d)
    assert src.id == "apple_docs"
    assert src.url == "https://developer.apple.com"
    assert src.max_depth == 3
    assert src.crawler == "playwright"


def test_crawl_source_defaults() -> None:
    src = crawl_source_from_dict({})
    assert src.id == ""
    assert src.url == ""
    assert src.max_depth == 2
