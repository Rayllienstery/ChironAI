"""Tests for create-collection embedding input safety helpers."""

from __future__ import annotations

from api.http.webui_crawler_routes import (
    _clip_text_for_embedding,
    _is_embed_context_length_error,
)


def test_clip_text_for_embedding_prefers_sentence_boundary() -> None:
    text = ("First sentence has useful context. " * 20) + "Trailing fragment without enough room"

    clipped = _clip_text_for_embedding(text, 220)

    assert len(clipped) <= 220
    assert clipped.endswith(".")
    assert "Trailing fragment" not in clipped


def test_clip_text_for_embedding_drops_open_code_fence_tail() -> None:
    text = "# API\n\nUseful explanation before code.\n\n```swift\n" + ("let value = 1\n" * 80)

    clipped = _clip_text_for_embedding(text, 220)

    assert len(clipped) <= 220
    assert clipped.count("```") % 2 == 0
    assert "Useful explanation" in clipped


def test_is_embed_context_length_error_detects_ollama_message() -> None:
    exc = RuntimeError("Ollama: the input length exceeds the context length")

    assert _is_embed_context_length_error(exc) is True
    assert _is_embed_context_length_error(RuntimeError("connection refused")) is False
