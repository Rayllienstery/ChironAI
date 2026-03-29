"""Tests for fetch_excerpt (mocked HTTP)."""

from __future__ import annotations

import requests

from web_interaction.fetch_excerpt import excerpt_url_allowed, fetch_page_excerpt


def test_excerpt_url_allowed() -> None:
    assert excerpt_url_allowed("https://developer.apple.com/documentation/SwiftUI") is True
    assert excerpt_url_allowed("https://www.swift.org/download/") is True
    assert excerpt_url_allowed("https://evil.com/") is False


def test_fetch_page_excerpt_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("WEB_INTERACTION_FETCH_PAGE", raising=False)
    t, u = fetch_page_excerpt("https://developer.apple.com/x")
    assert t == "" and u == ""


def test_fetch_page_excerpt_mocked(monkeypatch) -> None:
    monkeypatch.setenv("WEB_INTERACTION_FETCH_PAGE", "1")

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, _n=65536):
            yield b"<html><body><p>Official docs line.</p></body></html>"

    def fake_get(*_a, **_k):
        return Resp()

    monkeypatch.setattr(requests, "get", fake_get)
    t, u = fetch_page_excerpt("https://developer.apple.com/doc/foo")
    assert "Official" in t or "official" in t.lower()
    assert "developer.apple.com" in u
