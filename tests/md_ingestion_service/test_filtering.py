"""Tests for md_ingestion_service.domain.services.filtering."""

import pytest

from md_ingestion_service.domain.entities import FilterRule, MarkdownFile
from md_ingestion_service.domain.services.filtering import apply_filter, default_filter_rule


def test_apply_filter_include_exclude() -> None:
    rule = FilterRule(include_patterns=["**/*.md"], exclude_patterns=["**/nav.md"], min_size_chars=0, max_size_chars=0)
    assert apply_filter(MarkdownFile("s1", "page.md", "content", "page.md"), rule) is True
    assert apply_filter(MarkdownFile("s1", "nav.md", "content", "nav.md"), rule) is False


def test_apply_filter_min_size() -> None:
    rule = FilterRule(include_patterns=["**/*.md"], exclude_patterns=[], min_size_chars=10, max_size_chars=0)
    assert apply_filter(MarkdownFile("s1", "a.md", "short", "a.md"), rule) is False
    assert apply_filter(MarkdownFile("s1", "b.md", "long enough content", "b.md"), rule) is True


def test_default_filter_rule() -> None:
    r = default_filter_rule()
    assert r.include_patterns == ["**/*.md"]
    assert r.exclude_patterns == []
