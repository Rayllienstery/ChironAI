"""Build ProxyV2Wiring for the host app (Ollama client + settings + LlmProxy delegates)."""

from __future__ import annotations

from typing import Any

from flask import Flask

from config import get_ollama_chat_options, get_ollama_chat_url
from infrastructure.database import get_settings_repository
from infrastructure.ollama.openai_ollama_tool_bridge import (
    ollama_message_to_openai_assistant,
    ollama_tools_from_openai,
    openai_finish_reason_from_ollama,
    openai_messages_to_ollama,
)
from infrastructure.ollama.chat_client import OllamaChatClient
from llm_proxy.apply_edit import run_apply_file_edit
from llm_proxy.contracts import LlmProxyWiring
from llm_proxy.external_ingest import run_external_docs_ingest
from proxy_v2.contracts import ProxyV2Wiring

_PROXY_V2_MODEL_KEY = "proxy_v2_model"


def _pinned_model() -> str:
    try:
        return (get_settings_repository().get_app_setting(_PROXY_V2_MODEL_KEY) or "").strip()
    except Exception:
        return ""


def build_proxy_v2_wiring(app: Flask) -> ProxyV2Wiring:
    llm: LlmProxyWiring | None = app.extensions.get("llm_proxy_wiring")  # type: ignore[assignment]
    if llm is None:
        raise RuntimeError("Flask app missing extensions['llm_proxy_wiring']; create_app must set it")

    chat_url = get_ollama_chat_url()
    opts = get_ollama_chat_options()
    client = OllamaChatClient(base_url=chat_url, default_options=opts)

    def chat_api(body: dict[str, Any]) -> dict[str, Any]:
        return client.chat_api(body)

    def stream_final(body: dict[str, Any]) -> dict[str, Any]:
        return client.chat_api_stream_final(body)

    def iter_stream(body: dict[str, Any]):
        return client.iter_chat_api_stream_openai_parts(body)

    return ProxyV2Wiring(
        get_ollama_chat_url=lambda: str(get_ollama_chat_url()),
        get_pinned_model=_pinned_model,
        get_default_chat_options=lambda: dict(opts or {}),
        openai_messages_to_ollama=openai_messages_to_ollama,
        ollama_tools_from_openai=ollama_tools_from_openai,
        ollama_message_to_openai_assistant=ollama_message_to_openai_assistant,
        openai_finish_reason_from_ollama=openai_finish_reason_from_ollama,
        chat_api=chat_api,
        iter_chat_stream_openai_parts=iter_stream,
        chat_api_stream_final=stream_final,
        host_apply_file_edit=lambda: run_apply_file_edit(llm),
        host_external_docs_ingest=lambda: run_external_docs_ingest(llm),
    )


__all__ = ["build_proxy_v2_wiring", "_PROXY_V2_MODEL_KEY"]
