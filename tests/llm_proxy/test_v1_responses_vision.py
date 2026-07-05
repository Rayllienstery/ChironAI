from __future__ import annotations

from llm_proxy.openai_multipart_vision import (
    build_ollama_user_message_from_openai_content,
    collect_ollama_images_b64_from_parts,
)
from llm_proxy.v1_responses import (
    _responses_content_to_openai_user_content,
    _responses_input_to_openai_messages,
    _responses_request_to_openai_chat_body,
)

PNG_B64 = "aW1hZ2UtYnl0ZXM="
DATA_URL = f"data:image/png;base64,{PNG_B64}"


def test_responses_message_input_image_maps_to_openai_multipart() -> None:
    msgs = _responses_input_to_openai_messages(
        [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "describe this"},
                    {"type": "input_image", "image_url": DATA_URL},
                ],
            }
        ]
    )

    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "describe this"}
    assert content[1] == {"type": "image_url", "image_url": {"url": DATA_URL}}


def test_responses_shorthand_user_content_maps_input_image() -> None:
    msgs = _responses_input_to_openai_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "what is on the icon"},
                    {"type": "input_image", "image_url": {"url": DATA_URL}},
                ],
            }
        ]
    )

    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert isinstance(content, list)
    assert any(p.get("type") == "image_url" for p in content)


def test_responses_standalone_input_image_creates_user_message() -> None:
    msgs = _responses_input_to_openai_messages(
        [{"type": "input_image", "image_url": DATA_URL}]
    )

    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    content = msgs[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "image_url"


def test_responses_standalone_input_image_merges_into_prior_user_message() -> None:
    msgs = _responses_input_to_openai_messages(
        [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello"}]},
            {"type": "input_image", "image_url": DATA_URL},
        ]
    )

    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "hello"}
    assert content[1]["type"] == "image_url"


def test_responses_input_image_file_id_becomes_text_note() -> None:
    content = _responses_content_to_openai_user_content(
        [{"type": "input_image", "file_id": "file-abc123"}]
    )

    assert isinstance(content, str)
    assert "file_id" in content.lower()


def test_responses_request_body_preserves_images_for_ollama_mapping() -> None:
    body, _stream, _diag = _responses_request_to_openai_chat_body(
        {
            "model": "Agent-high",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "describe"},
                        {"type": "input_image", "image_url": DATA_URL},
                    ],
                }
            ],
        }
    )

    user_content = body["messages"][0]["content"]
    assert isinstance(user_content, list)
    images = collect_ollama_images_b64_from_parts(user_content)
    assert images == [PNG_B64]
    ollama_msg = build_ollama_user_message_from_openai_content(user_content)
    assert ollama_msg.get("images") == [PNG_B64]
