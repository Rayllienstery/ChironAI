from __future__ import annotations

from rag_service.infrastructure.openai_multipart_vision import (
    collect_ollama_images_b64_from_parts,
    promote_inline_data_image_urls_in_content,
    sanitize_proxy_content_parts,
)

PNG_B64 = "aW1hZ2UtYnl0ZXM="


def test_promote_inline_data_image_urls_converts_ai_sdk_file_and_image_parts() -> None:
    promoted = promote_inline_data_image_urls_in_content(
        [
            {"type": "text", "text": "describe"},
            {"type": "file", "mediaType": "image/png", "data": PNG_B64},
            {"type": "image", "mediaType": "image/jpeg", "image": PNG_B64},
        ]
    )

    assert promoted[0] == {"type": "text", "text": "describe"}
    assert promoted[1] == {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG_B64}"}}
    assert promoted[2] == {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{PNG_B64}"}}


def test_collect_ollama_images_reads_ai_sdk_parts_directly() -> None:
    images = collect_ollama_images_b64_from_parts(
        [
            {"type": "file", "mediaType": "image/png", "data": PNG_B64},
            {"type": "image", "mediaType": "image/png", "image": f"data:image/png;base64,{PNG_B64}"},
        ]
    )

    assert images == [PNG_B64, PNG_B64]


def test_sanitize_proxy_content_parts_keeps_valid_images_and_notes_invalid_data() -> None:
    sanitized = sanitize_proxy_content_parts(
        [
            {"type": "text", "text": "describe"},
            {"type": "file", "mediaType": "image/png", "data": PNG_B64},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,not-valid"}},
        ]
    )

    assert sanitized[0] == {"type": "text", "text": "describe"}
    assert sanitized[1] == {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG_B64}"}}
    assert sanitized[2]["type"] == "text"
    assert "invalid" in sanitized[2]["text"].lower()


def test_sanitize_proxy_content_parts_replaces_external_urls_by_default() -> None:
    sanitized = sanitize_proxy_content_parts(
        [{"type": "image_url", "image_url": {"url": "https://example.test/image.png"}}]
    )

    assert isinstance(sanitized, str)
    assert "external" in sanitized.lower()
    assert "data:image" in sanitized.lower()
