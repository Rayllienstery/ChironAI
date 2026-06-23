"""OpenAI/provider wire-format compatibility boundary for proxy chat behavior.

Provider-owned behavior lives in bundled LLM extensions (for example ``ollama-provider``).
This module is the intentional public ``/v1`` wire-format surface: it re-exports
OpenAI-shaped chat/tool/vision normalization helpers used while the proxy adapts
requests around provider-runtime calls. Do not add provider HTTP ownership here.
"""

from __future__ import annotations

from llm_proxy.openai_multipart_vision import (
    VISION_MAX_DECODED_BYTES,
    openai_parts_to_flat_text,
    promote_inline_data_image_urls_in_content,
    sanitize_openai_text_part,
    sanitize_proxy_content_parts,
)
from llm_proxy.openai_ollama_tool_bridge import (
    ollama_chat_tool_choice_payload_value,
    ollama_message_to_openai_assistant,
    ollama_tools_from_openai,
    openai_finish_reason_from_ollama,
    openai_tool_choice_means_none,
)
from llm_proxy.wire_format.gemini_model_id import is_gemini_family_model_name
from llm_proxy.wire_format.model_brand import resolve_brand_key
from llm_proxy.wire_format.model_capabilities import (
    caps_supports_thinking,
    caps_supports_tools,
    caps_supports_vision,
    chat_error_suggests_no_think,
    chat_error_suggests_no_tools,
    find_cached_ollama_vision_model,
    get_cached_ollama_capabilities,
)

__all__ = [
    "VISION_MAX_DECODED_BYTES",
    "caps_supports_thinking",
    "caps_supports_tools",
    "caps_supports_vision",
    "chat_error_suggests_no_think",
    "chat_error_suggests_no_tools",
    "find_cached_ollama_vision_model",
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
