"""Ollama management routes for WebUI."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from error_manager.http import error_response as _error_response

_WEBUI_LOG = logging.getLogger("webui")


def _get_ollama_url() -> str:
    """Ollama HTTP base for WebUI (model list, ping): same origin as RAG/chat (config), not ServiceStarter port 11343."""
    try:
        from config import get_ollama_base_url

        return get_ollama_base_url().rstrip("/")
    except Exception:
        return (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")


def _default_llm_provider_id() -> str:
    wiring = current_app.extensions.get("llm_proxy_wiring")
    provider_id = getattr(wiring, "default_provider_id", None)
    if isinstance(provider_id, str) and provider_id.strip():
        return provider_id.strip()
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    try:
        descriptors = runtime.registry.descriptors() if runtime is not None else []
    except Exception:
        descriptors = []
    if descriptors:
        first_id = str(descriptors[0].id or "").strip()
        if first_id:
            return first_id
    return ""


def _provider_catalog_payload(*, capability: str | None = None) -> dict[str, Any]:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    if svc is None:
        return {"providers": [], "models": []}
    try:
        return svc.provider_catalog(runtime=runtime, capability=capability)
    except Exception:
        return {"providers": [], "models": []}


def _provider_row(provider_id: str | None = None) -> dict[str, Any] | None:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    if svc is None:
        return None
    try:
        rows = svc.provider_rows(runtime)
    except Exception:
        return None
    resolved_provider_id = str(provider_id or _default_llm_provider_id()).strip()
    if resolved_provider_id:
        for row in rows:
            if str(row.get("provider_id") or "").strip() == resolved_provider_id:
                return row
    return rows[0] if rows else None


def _default_provider_row() -> dict[str, Any] | None:
    return _provider_row()


def _run_provider_extension_action(
    provider_id: str | None,
    action_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    row = _provider_row(provider_id)
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


def _run_default_provider_extension_action(action_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _run_provider_extension_action(_default_llm_provider_id(), action_id, payload)


def _default_provider_tab_payload() -> dict[str, Any]:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    row = _default_provider_row()
    if svc is None or runtime is None or row is None:
        raise RuntimeError("No default provider extension is available")
    extension_id = str(row.get("extension_id") or "").strip()
    if not extension_id:
        raise RuntimeError("Default provider extension is missing extension_id")
    return svc.extension_tab_payload(extension_id, runtime=runtime)


def _invoke_runtime_chat(
    *,
    provider_id: str,
    model: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
) -> str:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
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


def _shutdown_server() -> None:
    """
    Trigger server shutdown.

    - If running under Werkzeug dev server, call its shutdown hook.
    - Otherwise (e.g. started from a different WSGI runner), fall back to os._exit(0)
      to terminate the process on this request.
    """
    func = request.environ.get("werkzeug.server.shutdown")
    if func is not None:
        func()
        return

    # Fallback: hard-exit the process. This is acceptable here because this
    # server is intended for local/dev usage, started via start_webui.bat.
    os._exit(0)


def register_ollama_routes(
    bp: Blueprint,
    *,
    error_log: Any,
) -> None:
    """Register Ollama management routes on the given blueprint."""

    @bp.route("/ollama/status", methods=["GET"])
    def ollama_status() -> Any:
        """Legacy compatibility route backed by the default provider extension."""
        row = _default_provider_row()
        if row is None:
            return jsonify({"running": False, "error": "No default provider extension loaded"}), 503
        health = row.get("health") if isinstance(row.get("health"), dict) else {}
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        return jsonify(
            {
                "url": metadata.get("base_url") or metadata.get("chat_url") or None,
                "running": bool(health.get("ok")),
                "http_status": health.get("details", {}).get("status_code") if isinstance(health.get("details"), dict) else None,
                "error": health.get("message") or "",
            }
        )

    @bp.route("/ollama/start", methods=["POST"])
    def ollama_start() -> Any:
        try:
            result = _run_default_provider_extension_action("start_service")
            status = 200 if bool(result.get("ok")) else 500
            return jsonify({"ok": bool(result.get("ok")), "output": result.get("message") or ""}), status
        except Exception as e:
            _WEBUI_LOG.error("ollama_start: %s", e, exc_info=True)
            return jsonify({"ok": False, "output": str(e)}), 500

    @bp.route("/ollama/stop", methods=["POST"])
    def ollama_stop() -> Any:
        try:
            result = _run_default_provider_extension_action("stop_service")
            status = 200 if bool(result.get("ok")) else 500
            return jsonify({"ok": bool(result.get("ok")), "output": result.get("message") or ""}), status
        except Exception as e:
            _WEBUI_LOG.error("ollama_stop: %s", e, exc_info=True)
            return jsonify({"ok": False, "output": str(e)}), 500

    @bp.route("/ollama/library", methods=["GET"])
    def ollama_library() -> Any:
        try:
            payload = _default_provider_tab_payload()
            schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else {}
            rows: list[dict[str, Any]] = []
            hidden_ids: list[str] = []
            diagnostics = {}
            for page in schema.get("pages") or []:
                if not isinstance(page, dict):
                    continue
                for section in page.get("sections") or []:
                    if not isinstance(section, dict):
                        continue
                    for component in section.get("components") or []:
                        if not isinstance(component, dict):
                            continue
                        if component.get("type") == "table" and component.get("key") == "provider_models":
                            rows = [dict(item) for item in component.get("rows") or [] if isinstance(item, dict)]
                        if component.get("type") == "diagnostics":
                            diagnostics = dict(component.get("value") or {})
            if isinstance(diagnostics.get("hidden_model_ids"), list):
                hidden_ids = [str(x) for x in diagnostics.get("hidden_model_ids") if str(x).strip()]
            models = [
                {
                    "name": str(row.get("id") or ""),
                    "size": row.get("size", 0),
                    "modified_at": row.get("modified_at", ""),
                    "digest": row.get("digest"),
                    "hidden": bool(row.get("hidden")),
                }
                for row in rows
                if str(row.get("id") or "").strip()
            ]
            return jsonify({"ok": True, "url": diagnostics.get("base_url"), "models": models, "hidden_ids": hidden_ids})
        except Exception as e:
            _WEBUI_LOG.warning("ollama_library: %s", e)
            return jsonify(
                {
                    "ok": False,
                    "url": None,
                    "models": [],
                    "hidden_ids": [],
                    "error": str(e),
                }
            )

    @bp.route("/ollama/hidden", methods=["PATCH"])
    def ollama_hidden_patch() -> Any:
        body = request.get_json(silent=True) or {}
        raw_add = body.get("add")
        raw_remove = body.get("remove")
        add = raw_add if isinstance(raw_add, list) else []
        remove = raw_remove if isinstance(raw_remove, list) else []
        try:
            updated: list[str] = []
            for model_name in add:
                result = _run_default_provider_extension_action("hide_model", {"selected_model": str(model_name)})
                if isinstance(result.get("hidden_model_ids"), list):
                    updated = [str(x) for x in result.get("hidden_model_ids") if str(x).strip()]
            for model_name in remove:
                result = _run_default_provider_extension_action("unhide_model", {"selected_model": str(model_name)})
                if isinstance(result.get("hidden_model_ids"), list):
                    updated = [str(x) for x in result.get("hidden_model_ids") if str(x).strip()]
            return jsonify({"ok": True, "hidden_ids": updated})
        except Exception as e:
            _WEBUI_LOG.error("ollama_hidden_patch: %s", e, exc_info=True)
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/ollama/show", methods=["POST"])
    def ollama_show_model() -> Any:
        body = request.get_json(silent=True) or {}
        model = (body.get("model") or "").strip()
        if not model:
            return jsonify({"ok": False, "error": "model is required"}), 400
        try:
            result = _run_default_provider_extension_action("show_model", {"selected_model": model})
            return jsonify({"ok": bool(result.get("ok", True)), "details": result.get("details") or {}})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 502

    @bp.route("/ollama/delete", methods=["POST"])
    def ollama_delete_model() -> Any:
        body = request.get_json(silent=True) or {}
        model = (body.get("model") or "").strip()
        if not model:
            return jsonify({"ok": False, "error": "model is required"}), 400
        try:
            result = _run_default_provider_extension_action("delete_model", {"selected_model": model})
            return jsonify({"ok": bool(result.get("ok", True)), "result": result.get("details") or result.get("result") or {}})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 502

    @bp.route("/ollama/pull", methods=["POST"])
    def ollama_pull_stream() -> Any:
        body = request.get_json(silent=True) or {}
        model = (body.get("model") or "").strip()
        if not model:
            return _error_response("model is required", 400)

        def generate():
            try:
                result = _run_default_provider_extension_action("pull_model", {"pull_model_name": model})
                yield json.dumps(result, ensure_ascii=False) + "\n"
            except Exception as e:
                _WEBUI_LOG.error("ollama_pull_stream: %s", e, exc_info=True)
                yield json.dumps({"error": str(e)}) + "\n"

        return Response(
            stream_with_context(generate()),
            mimetype="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @bp.route("/server/stop", methods=["POST"])
    def server_stop() -> Any:
        """Stop the WebUI / RAG Proxy Flask server."""
        try:
            _WEBUI_LOG.info("Received WebUI shutdown request")
            _shutdown_server()
            return jsonify({"status": "stopping"})
        except Exception as e:
            error_log.error("webui_ollama_routes.server_stop", exc_info=True)
            return _error_response(e)
