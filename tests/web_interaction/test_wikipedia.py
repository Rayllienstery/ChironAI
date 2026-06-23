"""Tests for wikipedia_fallback (mocked HTTP)."""

from __future__ import annotations

from web_interaction.wikipedia_fallback import (
    fetch_wikipedia_supplement,
    wikipedia_question_eligible,
)


def test_wikipedia_eligible() -> None:
    assert wikipedia_question_eligible("When was Swift released?", "keywords") is True
    assert wikipedia_question_eligible("x", "low_confidence_framework") is False
    assert wikipedia_question_eligible("```swift\nx\n```", "keywords") is False


def test_fetch_wikipedia_disabled(monkeypatch) -> None:
    monkeypatch.delenv("WEB_INTERACTION_WIKIPEDIA", raising=False)
    assert fetch_wikipedia_supplement("Swift programming language") == ""


def test_fetch_wikipedia_mocked(monkeypatch) -> None:
    monkeypatch.setenv("WEB_INTERACTION_WIKIPEDIA", "1")

    class R1:
        def raise_for_status(self):
            pass

        def json(self):
            return ["q", ["Swift (programming language)"], [""], ["https://en.wikipedia.org/wiki/Swift_(programming_language)"]]

    class R2:
        def raise_for_status(self):
            pass

        def json(self):
            return {"extract": "Swift is a programming language."}

    calls = []

    def fake_get(url, **_k):
        calls.append(url)
        if "api.php" in url:
            return R1()
        return R2()

    monkeypatch.setattr("requests.get", fake_get)
    out = fetch_wikipedia_supplement("Tell me about Swift language")
    assert "Wikipedia" in out
    assert "Swift is" in out
