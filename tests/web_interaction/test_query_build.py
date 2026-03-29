"""Tests for web_interaction.query_build."""

from __future__ import annotations

from web_interaction.query_build import build_search_queries, strip_code_fences


def test_strip_code_fences() -> None:
    raw = "Hello ```swift\nlet x = 1\n``` world"
    assert "let x" not in strip_code_fences(raw)
    assert "Hello" in strip_code_fences(raw)
    assert "world" in strip_code_fences(raw)


def test_build_queries_keywords_single() -> None:
    qs = build_search_queries("What is the latest Xcode?", "keywords")
    assert len(qs) == 1
    assert "Xcode" in qs[0]


def test_build_queries_keywords_adds_release_when_version_hint() -> None:
    qs = build_search_queries("Does iOS 18 support widgets?", "keywords")
    joined = " ".join(qs).lower()
    assert "release" in joined


def test_build_queries_low_confidence_adds_site() -> None:
    qs = build_search_queries("SwiftUI List refreshable", "low_confidence_framework")
    assert len(qs) == 2
    assert "site:developer.apple.com" in qs[1]


def test_build_queries_empty_after_strip() -> None:
    assert build_search_queries("```\nonly code\n```", "keywords") == []


def test_build_web_supplement_multi_backend_low_conf_framework() -> None:
    from web_interaction.supplement import build_web_supplement_text

    calls: list[str] = []

    def backend(q: str, n: int):
        calls.append(q)
        return [{"title": "Doc", "url": "https://developer.apple.com/x", "body": "b"}]

    out = build_web_supplement_text(
        "SwiftUI NavigationStack",
        trigger="low_confidence_framework",
        search_backend=backend,
        max_n=2,
    )
    assert "developer.apple.com" in out
    assert len(calls) == 2
    assert any("site:developer.apple.com" in c for c in calls)
