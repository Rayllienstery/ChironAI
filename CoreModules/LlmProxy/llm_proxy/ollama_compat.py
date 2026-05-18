"""Temporary Ollama compatibility boundary for proxy chat behavior.

Ollama-owned behavior should live in the bundled ``ollama-provider`` extension.
These imports are kept here only to preserve public ``/v1/chat/completions``
compatibility while the proxy still normalizes OpenAI-shaped chat/tool/vision
payloads around provider-runtime calls.
"""

from __future__ import annotations

from infrastructure.ollama.gemini_model_id import is_gemini_family_model_name
from infrastructure.ollama.model_brand import resolve_brand_key
from infrastructure.ollama.model_capabilities import (
    caps_supports_thinking,
    caps_supports_tools,
    chat_error_suggests_no_think,
    chat_error_suggests_no_tools,
    get_cached_ollama_capabilities,
)
from infrastructure.ollama.openai_multipart_vision import (
    VISION_MAX_DECODED_BYTES,
    openai_parts_to_flat_text,
    promote_inline_data_image_urls_in_content,
    sanitize_openai_text_part,
    sanitize_proxy_content_parts,
)
from infrastructure.ollama.openai_ollama_tool_bridge import (
    ollama_chat_tool_choice_payload_value,
    ollama_message_to_openai_assistant,
    ollama_tools_from_openai,
    openai_finish_reason_from_ollama,
    openai_tool_choice_means_none,
)

__all__ = [
    "VISION_MAX_DECODED_BYTES",
    "caps_supports_thinking",
    "caps_supports_tools",
    "chat_error_suggests_no_think",
    "chat_error_suggests_no_tools",
    "get_cached_ollama_capabilities",
    "is_gemini_family_model_name",
    "ollama_chat_tool_choice_payload_value",
    "ollama_message_to_openai_assistant",
    "ollama_tools_from_openai",
    "openai_finish_reason_from_ollama",
    "openai_parts_to_flat_text",
    "openai_tool_choice_means_none",
    "promote_inline_data_image_urls_in_content",
    "resolve_brand_key",
    "sanitize_openai_text_part",
    "sanitize_proxy_content_parts",
]
