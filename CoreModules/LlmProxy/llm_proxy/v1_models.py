"""OpenAI-compatible model listing helpers for /v1 routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import get_v1_include_autocomplete_logical_model

if TYPE_CHECKING:
    from llm_proxy.contracts import LlmProxyWiring
def _openai_build_model_rows(wiring: LlmProxyWiring) -> list[dict[str, object]]:
    try:
        from application.llm_proxy_builds import (
            LLM_PROXY_BUILDS_APP_KEY,
            load_builds_json,
            openai_model_objects_for_builds,
        )

        repo = wiring.get_settings_repository()
        raw = repo.get_app_setting(LLM_PROXY_BUILDS_APP_KEY)
        builds = load_builds_json(raw)
        return openai_model_objects_for_builds(builds)
    except Exception:
        return []


def _openai_client_capability_model_row(model_id: str) -> dict[str, object]:
    from application.llm_proxy_builds import openai_client_capability_fields

    row: dict[str, object] = {
        "id": model_id,
        "object": "model",
        "created": 0,
        "owned_by": "local",
    }
    row.update(openai_client_capability_fields())
    return row


def _openai_autocomplete_model_row(wiring: LlmProxyWiring) -> dict[str, object]:
    row = _openai_client_capability_model_row(str(wiring.runtime.autocomplete_model_logical_id))
    row["metadata"] = {"ollama_model": str(wiring.get_autocomplete_ollama_model() or "")}
    return row


def _openai_model_rows(wiring: LlmProxyWiring) -> list[dict[str, object]]:
    data: list[dict[str, object]] = []
    if get_v1_include_autocomplete_logical_model():
        try:
            if wiring.get_autocomplete_ollama_model():
                data.append(_openai_autocomplete_model_row(wiring))
        except Exception:
            pass
    data.extend(_openai_build_model_rows(wiring))
    return data

__all__ = [
    "_openai_autocomplete_model_row",
    "_openai_build_model_rows",
    "_openai_client_capability_model_row",
    "_openai_model_rows",
]

