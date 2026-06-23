from __future__ import annotations

from llm_proxy.chat_completions_messages import _normalize_request_messages


def test_normalize_request_messages_drops_prior_transport_error_artifact() -> None:
    messages = _normalize_request_messages(
        {
            "messages": [
                {"role": "user", "content": "Что на картинке"},
                {
                    "role": "assistant",
                    "content": (
                        "[Error: 400 Client Error: Bad Request for url: "
                        "http://localhost:11434/api/chat]\n\n<dcp-message-id>m0004</dcp-message-id>"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Что на пикче?"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    "data:image/png;base64,"
                                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
                                )
                            },
                        },
                    ],
                },
            ]
        }
    )

    assert [m["role"] for m in messages] == ["user", "user"]
    assert messages[-1]["content"][0] == {"type": "text", "text": "Что на пикче?"}
    assert messages[-1]["content"][1]["type"] == "image_url"


def test_normalize_request_messages_keeps_non_artifact_assistant_error_discussion() -> None:
    messages = _normalize_request_messages(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": "The previous command printed [Error: 400 Client Error] because the endpoint rejected JSON.",
                }
            ]
        }
    )

    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"


def test_normalize_request_messages_drops_transport_error_from_multipart_assistant() -> None:
    messages = _normalize_request_messages(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "[Error: 500 Server Error: Internal Server Error for url: "
                                "http://localhost:8080/v1/chat/completions]"
                            ),
                        },
                        {"type": "text", "text": "<dcp-message-id>m999</dcp-message-id>"},
                    ],
                },
                {"role": "user", "content": "retry"},
            ]
        }
    )

    assert messages == [{"role": "user", "content": "retry"}]


def test_normalize_request_messages_keeps_user_transport_error_text() -> None:
    messages = _normalize_request_messages(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "[Error: 400 Client Error: Bad Request for url: http://localhost:11434/api/chat]",
                }
            ]
        }
    )

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert "Client Error" in messages[0]["content"]


def test_normalize_request_messages_prompt_suffix_and_input_fallbacks() -> None:
    assert _normalize_request_messages({"prompt": "hello", "suffix": "world"}) == [
        {"role": "user", "content": "hello\nworld"}
    ]
    assert _normalize_request_messages({"prompt": ["he", "llo", 42]}) == [
        {"role": "user", "content": "hello"}
    ]
    assert _normalize_request_messages({"input": "from responses"}) == [
        {"role": "user", "content": "from responses"}
    ]
    assert _normalize_request_messages({"messages": [], "prompt": "", "input": ""}) == []
