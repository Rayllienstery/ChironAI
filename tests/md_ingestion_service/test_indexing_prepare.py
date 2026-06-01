"""Tests for prepare_markdown_for_indexing and strip_noise_section_headings."""

from __future__ import annotations

import pytest

from md_ingestion_service.domain.services.indexing_prepare import (
    apply_source_prepare_options,
    prepare_markdown_for_indexing,
    strip_leading_toc,
    strip_noise_section_headings,
    strip_store_cta_lines,
)


def test_strip_noise_removes_section() -> None:
    md = """# Title

## Topics

Hello

## Conforming Types

Foo bar

## See Also

Tail
"""
    out = strip_noise_section_headings(md, ["Conforming Types"])
    assert "Foo bar" not in out
    assert "See Also" in out
    assert "Topics" in out


def _meta_body(url: str, body: str) -> str:
    return f"<!-- \nurl: {url}\n-->\n\n{body}"


def test_prepare_filename_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "md_ingestion_service.domain.services.indexing_prepare.get_indexing_list",
        lambda k, d: ["badslug"] if k == "exclude_filename_substrings" else (d if isinstance(d, list) else []),
    )
    monkeypatch.setattr(
        "md_ingestion_service.domain.services.indexing_prepare.get_indexing_int",
        lambda k, d: d,
    )
    raw = _meta_body("https://x", "word " * 200)
    r = prepare_markdown_for_indexing("page-badslug-abc.md", raw, run_pipeline_fn=None, active_pipeline_name_fn=None)
    assert r.skipped is True
    assert r.skip_reason == "filename_excluded"


def test_prepare_content_head_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "md_ingestion_service.domain.services.indexing_prepare.get_indexing_list",
        lambda k, d: (["DEVELOPER STORIES"] if k == "exclude_content_substrings" else (d if isinstance(d, list) else [])),
    )
    monkeypatch.setattr(
        "md_ingestion_service.domain.services.indexing_prepare.get_indexing_int",
        lambda k, d: 2000 if k == "exclude_content_head_chars" else d,
    )
    raw = _meta_body("https://x", "DEVELOPER STORIES\n\n" + ("body " * 100))
    r = prepare_markdown_for_indexing("ok.md", raw, run_pipeline_fn=None, active_pipeline_name_fn=None)
    assert r.skipped is True
    assert r.skip_reason == "content_excluded"


def test_prepare_reject_low_signal_too_short(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "md_ingestion_service.domain.services.indexing_prepare.get_indexing_list",
        lambda k, d: [],
    )
    monkeypatch.setattr(
        "md_ingestion_service.domain.services.indexing_prepare.get_indexing_int",
        lambda k, d: d,
    )
    raw = _meta_body("https://x", "short")
    r = prepare_markdown_for_indexing("x.md", raw, run_pipeline_fn=None, active_pipeline_name_fn=None)
    assert r.skipped is True
    assert r.skip_reason == "empty_after_prepare"


def test_strip_leading_toc_removes_nav_before_h1() -> None:
    md = """[Home](/)
[Example code](/example-code)

# NavigationStack

Real content here with enough words to matter for the article body.
"""
    out = strip_leading_toc(md)
    assert out.startswith("# NavigationStack")
    assert "[Home]" not in out


def test_strip_store_cta_removes_sponsor_lines() -> None:
    md = """# Title

Good paragraph with technical content about SwiftUI navigation patterns.

Please sponsor the site today.

More content.
"""
    out = strip_store_cta_lines(md)
    assert "sponsor" not in out.lower()
    assert "Good paragraph" in out


def test_apply_source_prepare_options_hws() -> None:
    md = """[Nav](/)

# How to push a view

Body text about NavigationStack push navigation in SwiftUI apps.
"""
    out = apply_source_prepare_options(
        md,
        {"strip_toc": True, "strip_store_cta": True},
    )
    assert out.startswith("# How to push")


def test_prepare_happy_path_no_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "md_ingestion_service.domain.services.indexing_prepare.get_indexing_list",
        lambda k, d: [],
    )
    monkeypatch.setattr(
        "md_ingestion_service.domain.services.indexing_prepare.get_indexing_int",
        lambda k, d: d,
    )
    raw = _meta_body("https://developer.apple.com/doc", "paragraph " * 50)
    r = prepare_markdown_for_indexing("page.md", raw, run_pipeline_fn=None, active_pipeline_name_fn=None)
    assert r.skipped is False
    assert r.body_md
    assert "paragraph" in r.body_md
    assert r.page_meta.get("url") == "https://developer.apple.com/doc"
