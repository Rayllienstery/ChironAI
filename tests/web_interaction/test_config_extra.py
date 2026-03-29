"""Tests for web_interaction.config helpers."""

from __future__ import annotations

from web_interaction.config import ddg_news_enabled, ddg_region_for_message


def test_ddg_region_explicit(monkeypatch) -> None:
    monkeypatch.setenv("WEB_INTERACTION_DDG_REGION", "de-de")
    assert ddg_region_for_message("hello") == "de-de"
    monkeypatch.delenv("WEB_INTERACTION_DDG_REGION", raising=False)


def test_ddg_region_cyrillic_default(monkeypatch) -> None:
    monkeypatch.delenv("WEB_INTERACTION_DDG_REGION", raising=False)
    assert ddg_region_for_message("Когда вышла iOS 18?") == "ru-ru"


def test_ddg_region_none_for_ascii(monkeypatch) -> None:
    monkeypatch.delenv("WEB_INTERACTION_DDG_REGION", raising=False)
    assert ddg_region_for_message("latest Swift") is None


def test_ddg_news_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("WEB_INTERACTION_DDG_NEWS", raising=False)
    assert ddg_news_enabled() is False


def test_ddg_news_enabled(monkeypatch) -> None:
    monkeypatch.setenv("WEB_INTERACTION_DDG_NEWS", "1")
    assert ddg_news_enabled() is True
    monkeypatch.delenv("WEB_INTERACTION_DDG_NEWS", raising=False)
