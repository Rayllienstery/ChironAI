"""Tests for web_interaction.cache."""

from __future__ import annotations

import os

from web_interaction.cache import cache_clear_for_tests, cache_get, cache_set, make_cache_key


def teardown_function() -> None:
    cache_clear_for_tests()
    os.environ.pop("WEB_INTERACTION_CACHE_TTL_S", None)


def test_cache_roundtrip(monkeypatch) -> None:
    monkeypatch.setenv("WEB_INTERACTION_CACHE_TTL_S", "60")
    cache_clear_for_tests()
    key = make_cache_key(["q1"], "keywords", 3, "", variant="news0")
    snippets = [{"title": "T", "url": "https://u", "body": "b"}]
    assert cache_get(key) is None
    cache_set(key, snippets, {"ddg_news": True})
    got = cache_get(key)
    assert got is not None
    ranked, aux = got
    assert len(ranked) == 1
    assert ranked[0]["url"] == "https://u"
    assert aux.get("ddg_news") is True


def test_cache_disabled_zero_ttl(monkeypatch) -> None:
    monkeypatch.setenv("WEB_INTERACTION_CACHE_TTL_S", "0")
    cache_clear_for_tests()
    key = make_cache_key(["q"], "keywords", 1, "", variant="news0")
    cache_set(key, [{"title": "x", "url": "https://a", "body": ""}], {})
    assert cache_get(key) is None
