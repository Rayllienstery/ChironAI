"""Tests for web_interaction.ranking."""

from __future__ import annotations

from web_interaction.ranking import rank_and_trim, top_domains


def test_rank_prefers_apple_docs() -> None:
    snippets = [
        {"title": "Spam", "url": "https://random-blog.example/p", "body": "x"},
        {"title": "Apple", "url": "https://developer.apple.com/doc", "body": "official"},
    ]
    out = rank_and_trim(snippets, max_n=1)
    assert len(out) == 1
    assert "developer.apple.com" in (out[0].get("url") or "")


def test_rank_drops_blocklisted() -> None:
    snippets = [
        {"title": "P", "url": "https://pinterest.com/pin/1", "body": "a"},
        {"title": "G", "url": "https://github.com/a/b", "body": "b"},
    ]
    out = rank_and_trim(snippets, max_n=2)
    assert len(out) == 1
    assert "github.com" in (out[0].get("url") or "")


def test_top_domains() -> None:
    s = [
        {"url": "https://a.example/x"},
        {"url": "https://b.example/y"},
    ]
    assert top_domains(s, 2) == ["a.example", "b.example"]


def test_preferred_domains_env(monkeypatch) -> None:
    monkeypatch.setenv("WEB_INTERACTION_PREFERRED_DOMAINS", "swift.org,example.org")
    s = [
        {"title": "E", "url": "https://foo.example.org/z", "body": "x"},
        {"title": "S", "url": "https://swift.org/y", "body": "longer swift body wins tie-break"},
    ]
    out = rank_and_trim(s, max_n=1)
    assert "swift.org" in (out[0].get("url") or "")
