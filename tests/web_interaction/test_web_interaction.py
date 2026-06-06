"""Unit tests for CoreModules/WebInteraction (no network)."""

from __future__ import annotations

from web_interaction.format import format_web_supplement
from web_interaction.supplement import build_web_supplement_bundle, build_web_supplement_text, should_fetch_web_supplement
from web_interaction.triggers import decide_trigger, looks_like_framework_question, wants_freshness_or_release


def test_wants_freshness_latest() -> None:
    assert wants_freshness_or_release("What is the latest Swift version?") is True


def test_wants_freshness_current_word() -> None:
    assert wants_freshness_or_release("What is the current iOS version?") is True


def test_wants_freshness_ios_version() -> None:
    assert wants_freshness_or_release("Does iOS 26 support X?") is True


def test_framework_question() -> None:
    assert looks_like_framework_question("How do I use SwiftUI List?") is True
    assert looks_like_framework_question("Hello") is False


def test_decide_trigger_keywords() -> None:
    t = decide_trigger(
        "What is the latest iOS?",
        on_keywords=True,
        on_low_confidence_framework=True,
        max_score=0.9,
        confidence_threshold=0.5,
    )
    assert t == "keywords"


def test_decide_trigger_low_conf_framework() -> None:
    t = decide_trigger(
        "SwiftUI navigation stack",
        on_keywords=False,
        on_low_confidence_framework=True,
        max_score=0.1,
        confidence_threshold=0.5,
    )
    assert t == "low_confidence_framework"


def test_decide_trigger_none_when_score_high() -> None:
    t = decide_trigger(
        "SwiftUI navigation stack",
        on_keywords=False,
        on_low_confidence_framework=True,
        max_score=0.9,
        confidence_threshold=0.5,
    )
    assert t == "none"


def test_should_fetch_respects_master_flag() -> None:
    ok, tr = should_fetch_web_supplement(
        "latest version of Swift",
        master_enabled=False,
        on_keywords=True,
        on_low_confidence_framework=True,
        max_score=0.0,
        confidence_threshold=0.9,
    )
    assert ok is False
    assert tr == "none"


def test_format_web_supplement() -> None:
    text = format_web_supplement(
        [{"title": "A", "url": "https://a.example", "body": "snippet"}],
        iso_date="2026-01-01 00:00 UTC",
    )
    assert "Additional context from web search" in text
    assert "https://a.example" in text
    assert "snippet" in text


def test_build_web_supplement_text_mock_backend() -> None:
    def backend(q: str, n: int):
        return [{"title": "T", "url": "https://u", "body": "B"}]

    out = build_web_supplement_text("query", search_backend=backend, max_n=2)
    assert "https://u" in out


def test_build_web_supplement_text_empty_backend() -> None:
    def backend(q: str, n: int):
        return []

    assert build_web_supplement_text("x", search_backend=backend) == ""


def test_build_web_supplement_bundle_ddg_news_kwarg_false() -> None:
    def backend(q: str, n: int):
        return [{"title": "T", "url": "https://u", "body": "B"}]

    _text, meta = build_web_supplement_bundle(
        "What is the latest iOS?",
        trigger="keywords",
        max_n=2,
        search_backend=backend,
        ddg_news=False,
    )
    assert meta["ddg_news"] is False
