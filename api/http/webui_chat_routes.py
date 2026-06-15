"""Core WebUI chat and model list routes."""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable

from error_manager.http import error_response as _error_response
from flask import jsonify, request
from llm_proxy.config import AUTOCOMPLETE_MODEL_ID

from api.http.proxy_status import STATUS_IDLE
from api.http.webui_session import log_to_database
from config import get_rag_float, get_rag_int
from infrastructure.database import get_settings_repository

_REQUEST_BUFFER: deque[dict[str, Any]] = deque(maxlen=50)


def register_chat_routes(
    bp: Any,
    *,
    error_log: Any,
    provider_catalog_payload: Callable[..., dict[str, Any]],
    default_llm_provider_id: Callable[[], str],
    config_default_chat_model: Callable[[], str],
    run_unified_proxy_chat: Callable[[dict[str, Any]], Any],
    set_proxy_status: Callable[[str], None],
    set_latest_request_seconds: Callable[[float], None],
) -> None:
    @bp.route("/models", methods=["GET"])
    def get_models() -> Any:
        try:
            catalog = provider_catalog_payload(capability="chat")
            models_list: list[dict[str, Any]] = []
            for model in catalog.get("models") or []:
                if not isinstance(model, dict):
                    continue
                model_id = str(model.get("id") or "").strip()
                provider_id = str(model.get("provider_id") or "").strip()
                if not model_id:
                    continue
                models_list.append(
                    {
                        "id": model_id,
                        "name": model.get("label") or model_id,
                        "description": model.get("description") or f"{provider_id} model: {model_id}",
                        "provider_id": provider_id,
                        "provider_title": model.get("provider_title") or provider_id,
                        "size": (model.get("metadata") or {}).get("size", 0),
                        "modified_at": (model.get("metadata") or {}).get("modified_at", ""),
                    }
                )
            if not models_list:
                model_name = config_default_chat_model()
                models_list.append(
                    {
                        "id": model_name,
                        "name": model_name,
                        "description": f"Default model: {model_name}",
                        "provider_id": default_llm_provider_id(),
                        "provider_title": default_llm_provider_id(),
                    }
                )

            try:
                settings_repo = get_settings_repository()
                if (settings_repo.get_app_setting("proxy_autocomplete_model") or "").strip():
                    models_list.insert(
                        0,
                        {
                            "id": AUTOCOMPLETE_MODEL_ID,
                            "name": AUTOCOMPLETE_MODEL_ID,
                            "description": "Autocomplete (maps to LLM Proxy → Autocomplete provider/model)",
                            "provider_id": str(
                                settings_repo.get_app_setting("proxy_autocomplete_provider_id") or ""
                            ).strip()
                            or default_llm_provider_id(),
                        },
                    )
            except Exception:
                pass

            return jsonify({"models": models_list})
        except Exception as e:
            error_log.error("webui_chat_routes.get_models", exc_info=True)
            log_to_database("ERROR", str(e), source="webui_chat_routes.get_models", error_type=type(e).__name__)
            return _error_response(e)

    @bp.route("/config", methods=["GET"])
    def get_config() -> Any:
        try:
            return jsonify({
                "context_chunk_chars": get_rag_int("context_chunk_chars", 1000),
                "context_total_chars": get_rag_int("context_total_chars", 7000),
                "top_k": get_rag_int("top_k", 4),
                "confidence_threshold": get_rag_float("confidence_threshold", 0.75),
                "model_name": config_default_chat_model(),
            })
        except Exception as e:
            error_log.error("webui_chat_routes.get_config", exc_info=True)
            return _error_response(e)

    @bp.route("/chat", methods=["POST"])
    def webui_chat() -> Any:
        start_time = time.time()
        try:
            body = request.get_json(force=True, silent=True) or {}
            messages = body.get("messages") or []
            if not messages:
                return _error_response("messages is required", 400)

            proxy_body: dict[str, Any] = dict(body)
            proxy_body["messages"] = messages
            proxy_body["stream"] = False
            if "include_rag_metadata" not in proxy_body:
                proxy_body["include_rag_metadata"] = True
            if bool(body.get("code_only")) and isinstance(proxy_body.get("messages"), list):
                _msgs = [m for m in proxy_body.get("messages", []) if isinstance(m, dict)]
                if _msgs:
                    for i in range(len(_msgs) - 1, -1, -1):
                        if str(_msgs[i].get("role") or "") == "user":
                            _c = str(_msgs[i].get("content") or "")
                            _msgs[i] = dict(_msgs[i], content=f"Only code, no explanations. {_c}".strip())
                            break
                    proxy_body["messages"] = _msgs
            return run_unified_proxy_chat(proxy_body)

        except Exception as e:
            error_log.error("webui_chat_routes.webui_chat", exc_info=True)
            log_to_database("ERROR", str(e), source="webui_chat_routes.webui_chat", error_type=type(e).__name__)
            return _error_response(e)
        finally:
            set_proxy_status(STATUS_IDLE)
            set_latest_request_seconds(time.time() - start_time)

    @bp.route("/dev-console", methods=["GET"])
    def get_dev_console() -> Any:
        try:
            limit = int(request.args.get("limit", 20))
            return jsonify({
                "requests": list(_REQUEST_BUFFER)[-limit:],
            })
        except Exception as e:
            error_log.error("webui_chat_routes.get_dev_console", exc_info=True)
            return _error_response(e)
