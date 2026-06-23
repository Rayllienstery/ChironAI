"""Shared WebUI provider catalog and LLM runtime helpers."""

from __future__ import annotations

from typing import Any

from flask import current_app

from api.http.extensions_service_access import get_extensions_runtime, get_extensions_service


def default_llm_provider_id() -> str:
    wiring = current_app.extensions.get("llm_proxy_wiring")
    provider_id = getattr(wiring, "default_provider_id", None)
    if isinstance(provider_id, str) and provider_id.strip():
        return provider_id.strip()
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
    try:
        descriptors = runtime.registry.descriptors() if runtime is not None else []
    except Exception:
        descriptors = []
    if descriptors:
        first_id = str(descriptors[0].id or "").strip()
        if first_id:
            return first_id
    return ""


def provider_catalog_payload(*, capability: str | None = None) -> dict[str, Any]:
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
    if svc is None:
        return {"providers": [], "models": []}
    try:
        return svc.provider_catalog(runtime=runtime, capability=capability)
    except Exception:
        return {"providers": [], "models": []}


def provider_row(provider_id: str | None = None) -> dict[str, Any] | None:
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
    if svc is None:
        return None
    try:
        rows = svc.provider_rows(runtime)
    except Exception:
        return None
    resolved_provider_id = str(provider_id or default_llm_provider_id()).strip()
    if resolved_provider_id:
        for row in rows:
            if str(row.get("provider_id") or "").strip() == resolved_provider_id:
                return row
    return rows[0] if rows else None


def default_provider_row() -> dict[str, Any] | None:
    return provider_row()


def run_provider_extension_action(
    provider_id: str | None,
    action_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
    row = provider_row(provider_id)
    if svc is None or runtime is None or row is None:
        raise RuntimeError("No provider extension is available")
    extension_id = str(row.get("extension_id") or "").strip()
    if not extension_id:
        raise RuntimeError("Provider extension is missing extension_id")
    return svc.run_extension_action(
        extension_id,
        action_id,
        payload=dict(payload or {}),
        runtime=runtime,
    )


def run_default_provider_extension_action(action_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return run_provider_extension_action(default_llm_provider_id(), action_id, payload)


def default_provider_tab_payload() -> dict[str, Any]:
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
    row = default_provider_row()
    if svc is None or runtime is None or row is None:
        raise RuntimeError("No default provider extension is available")
    extension_id = str(row.get("extension_id") or "").strip()
    if not extension_id:
        raise RuntimeError("Default provider extension is missing extension_id")
    return svc.extension_tab_payload(extension_id, runtime=runtime)


def invoke_runtime_chat(
    *,
    provider_id: str,
    model: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
) -> str:
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
    if runtime is None:
        raise RuntimeError("LLM runtime is unavailable")
    from llm_interactor.contracts import LLMRequest

    response = runtime.invoke(
        LLMRequest(
            provider_id=provider_id,
            model=model,
            operation="chat",
            messages=[m for m in messages if isinstance(m, dict)],
            stream=False,
            options=(options or None),
        )
    )
    return str(response.text or "")


def invoke_runtime_embed(
    *,
    provider_id: str,
    model: str,
    texts: list[str],
) -> list[list[float]]:
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
    if runtime is None:
        raise RuntimeError("LLM runtime is unavailable")
    from llm_interactor.contracts import LLMRequest

    response = runtime.invoke(
        LLMRequest(
            provider_id=provider_id,
            model=model,
            operation="embed",
            input_texts=[str(text) for text in texts],
        )
    )
    raw = response.raw if isinstance(response.raw, dict) else {}
    embeddings = raw.get("embeddings")
    if not isinstance(embeddings, list):
        raise RuntimeError("Provider returned invalid embeddings payload")
    out: list[list[float]] = []
    for item in embeddings:
        if isinstance(item, list):
            out.append([float(v) for v in item])
    if len(out) != len(texts):
        raise RuntimeError(f"Expected {len(texts)} embeddings, got {len(out)}")
    return out


def read_app_provider_model_ref(
    settings_repo: Any,
    *,
    provider_key: str,
    model_key: str,
    fallback_provider: str | None = None,
) -> tuple[str, str]:
    provider_id = str(settings_repo.get_app_setting(provider_key) or "").strip()
    model = str(settings_repo.get_app_setting(model_key) or "").strip()
    if model and not provider_id:
        provider_id = str(fallback_provider or default_llm_provider_id()).strip()
    return provider_id, model


def run_unified_proxy_chat(body: dict[str, Any]) -> Any:
    """Delegate chat handling to /v1 chat_completions core to avoid duplicate RAG logic."""
    from error_manager.http import error_response as _error_response

    wiring = current_app.extensions.get("llm_proxy_wiring")
    if wiring is None:
        return _error_response("LLM proxy wiring not initialized", 500)
    from llm_proxy.chat_completions import run_chat_completions

    return run_chat_completions(wiring, body_override=body)
