"""Model settings and Model Tester routes for the WebUI blueprint."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable

from flask import Blueprint, current_app, jsonify, request

from api.http.extensions_service_access import get_extensions_runtime, get_extensions_service
from chironai_rag.bindings import ConsumerRagBindings
from chironai_rag.consumers import RAG_COLLECTION_APP_SETTING, RagConsumer
from config import get_rag_float, get_rag_int, get_rag_prompt_name
from config.rag_prompts import get_rag_system_prompt, rag_prompt_file_exists
from error_manager.http import error_response as _error_response
from infrastructure.database import get_settings_repository
from rag_service.application.params import get_rag_answer_params
from rag_service.domain.services.prompt_builder import build_system_content
from webui_backend.paths import webui_data_dir

from api.http.webui_prompts import is_readme_name


def register_model_tester_routes(
    bp: Blueprint,
    *,
    error_log: Any,
    run_unified_proxy_chat: Callable[[dict[str, Any]], Any],
    default_llm_provider_id: Callable[[], str],
    read_app_provider_model_ref: Callable[..., tuple[str, str]],
    get_qdrant_collection_names: Callable[[], list[str]],
    config_default_chat_model: Callable[[], str],
) -> None:
    @bp.route("/model-settings", methods=["GET"])
    def get_model_settings() -> Any:
        """Get current model settings."""
        try:
            settings_repo = get_settings_repository()
            default_provider_id = default_llm_provider_id()
            stored_provider_id, stored_model = read_app_provider_model_ref(
                settings_repo,
                provider_key="proxy_provider_id",
                model_key="proxy_model",
                fallback_provider=default_provider_id,
            )
            stored_settings_json = settings_repo.get_app_setting("proxy_settings")
            stored_rag_col = (settings_repo.get_app_setting(RAG_COLLECTION_APP_SETTING) or "").strip()
            stored_autocomplete_provider_id, stored_autocomplete = read_app_provider_model_ref(
                settings_repo,
                provider_key="proxy_autocomplete_provider_id",
                model_key="proxy_autocomplete_model",
                fallback_provider=default_provider_id,
            )

            out: dict[str, Any] = {
                "provider_id": stored_provider_id,
                "model": stored_model,
                "autocomplete_provider_id": stored_autocomplete_provider_id,
                "prompt_name": "",
                "temperature": get_rag_float("temperature", 0.0),
                "top_p": get_rag_float("top_p", 0.1),
                "reasoning_level": "",
                "code_only": False,
                "include_rag_metadata": True,
                "fetch_web_knowledge": False,
                "web_interaction_enabled": False,
                "web_interaction_on_keywords": True,
                "web_interaction_on_low_confidence_framework": True,
                "web_interaction_ddg_news": False,
                "web_interaction_fetch_page": False,
                "web_interaction_wikipedia": False,
                "rag_collection": stored_rag_col,
                "autocomplete_model": stored_autocomplete,
            }

            if stored_settings_json:
                try:
                    blob = json.loads(stored_settings_json)
                    for key, val in blob.items():
                        if key in out:
                            out[key] = val
                        elif key == "model" and not out["model"]:
                            out["model"] = str(val or "").strip()
                    if not out["provider_id"] and out["model"]:
                        out["provider_id"] = default_provider_id
                    if not out["autocomplete_provider_id"] and out["autocomplete_model"]:
                        out["autocomplete_provider_id"] = default_provider_id
                except json.JSONDecodeError:
                    pass

            pn = str(out.get("prompt_name") or "").strip()
            try:
                q_names = set(get_qdrant_collection_names() or [])
            except Exception:
                q_names = set()
            rc = str(out.get("rag_collection") or "").strip()

            out["model_missing"] = not out["model"]
            out["prompt_missing"] = (not pn) or (not rag_prompt_file_exists(pn)) or is_readme_name(pn)
            out["collection_missing"] = bool(rc) and bool(q_names) and rc not in q_names

            return jsonify(out)
        except Exception as e:
            error_log.error("webui_model_tester_routes.get_model_settings", exc_info=True)
            return _error_response(e)

    @bp.route("/model-settings", methods=["POST"])
    def update_model_settings() -> Any:
        """Update model settings (persisted to app_settings)."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            settings_repo = get_settings_repository()
            if body.get("provider_id") is not None:
                settings_repo.set_app_setting("proxy_provider_id", str(body.get("provider_id") or "").strip())
            if body.get("model") is not None:
                settings_repo.set_app_setting("proxy_model", str(body["model"]))
            if body.get("autocomplete_provider_id") is not None:
                settings_repo.set_app_setting(
                    "proxy_autocomplete_provider_id",
                    str(body.get("autocomplete_provider_id") or "").strip(),
                )
            if body.get("autocomplete_model") is not None:
                settings_repo.set_app_setting("proxy_autocomplete_model", str(body.get("autocomplete_model") or "").strip())
            if body.get("rag_collection") is not None:
                ConsumerRagBindings(settings_repo).set_stored_collection(
                    RagConsumer.LLM_PROXY, str(body.get("rag_collection") or "").strip()
                )
            existing_blob: dict[str, Any] = {}
            try:
                raw_ps = settings_repo.get_app_setting("proxy_settings")
                if raw_ps:
                    existing_blob = json.loads(raw_ps)
                    if not isinstance(existing_blob, dict):
                        existing_blob = {}
            except (json.JSONDecodeError, TypeError):
                existing_blob = {}
            merged = {
                **existing_blob,
                **{
                    k: v
                    for k, v in body.items()
                    if k not in {"provider_id", "autocomplete_provider_id"}
                },
            }
            settings_repo.set_app_setting("proxy_settings", json.dumps(merged))
            return jsonify({"status": "ok", "settings": merged})
        except Exception as e:
            error_log.error("webui_model_tester_routes.update_model_settings", exc_info=True)
            return _error_response(e)

    @bp.route("/tester-settings", methods=["GET"])
    def get_tester_settings() -> Any:
        """Get Model Tester settings for a session."""
        try:
            session_id = request.args.get("session_id")
            if not session_id:
                return _error_response("session_id is required", 400)

            settings_repo = get_settings_repository()
            settings = settings_repo.get_tester_settings(session_id)

            if not settings:
                return jsonify({
                    "model": "",
                    "prompt_name": "",
                    "temperature": 0.0,
                    "top_p": 0.1,
                    "reasoning_level": "",
                    "use_rag": True,
                    "top_k": get_rag_int("top_k", 4),
                    "rag_collection": "",
                    "fetch_web_knowledge": False,
                })

            if "rag_collection" not in settings:
                settings["rag_collection"] = ""
            if "fetch_web_knowledge" not in settings:
                settings["fetch_web_knowledge"] = False

            return jsonify(settings)
        except Exception as e:
            error_log.error("webui_model_tester_routes.get_tester_settings", exc_info=True)
            return _error_response(e)

    @bp.route("/tester-settings", methods=["POST"])
    def update_tester_settings() -> Any:
        """Save Model Tester settings for a session."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            session_id = body.get("session_id")

            if not session_id:
                return _error_response("session_id is required", 400)

            settings_repo = get_settings_repository()
            settings_repo.save_tester_settings(session_id, body)

            return jsonify({"status": "ok"})
        except Exception as e:
            error_log.error("webui_model_tester_routes.update_tester_settings", exc_info=True)
            return _error_response(e)

    @bp.route("/tester/chat", methods=["POST"])
    def tester_chat() -> Any:
        """Model Tester chat endpoint (with or without RAG)."""
        start_time = time.time()
        try:
            body = request.get_json(force=True, silent=True) or {}
            session_id = body.get("session_id")
            messages = body.get("messages") or []
            use_rag = body.get("use_rag", True)
            fetch_web_knowledge = body.get("fetch_web_knowledge", False)
            provider_id = str(body.get("provider_id") or "").strip()
            model = body.get("model")
            prompt_name = body.get("prompt_name")
            temperature = body.get("temperature")
            top_p = body.get("top_p")
            reasoning_level = body.get("reasoning_level")
            top_k = body.get("top_k")

            if not messages:
                return _error_response("messages is required", 400)

            if not session_id:
                return _error_response("session_id is required", 400)

            settings_repo = get_settings_repository()
            tester_settings = settings_repo.get_tester_settings(session_id) if session_id else None
            if tester_settings:
                provider_id = provider_id or str(tester_settings.get("provider_id") or "").strip()
                model = model or tester_settings.get("model")
                prompt_name = prompt_name or tester_settings.get("prompt_name")
                temperature = temperature if temperature is not None else tester_settings.get("temperature")
                top_p = top_p if top_p is not None else tester_settings.get("top_p")
                reasoning_level = reasoning_level or tester_settings.get("reasoning_level")
                use_rag = use_rag if "use_rag" in body else tester_settings.get("use_rag", True)
                top_k = top_k if top_k is not None else tester_settings.get("top_k")
                if "fetch_web_knowledge" not in body:
                    fetch_web_knowledge = tester_settings.get("fetch_web_knowledge", False)
            if not (str(model).strip() if model is not None else ""):
                model = (settings_repo.get_app_setting("proxy_model") or "").strip() or model

            collection_name = (body.get("collection_name") or "").strip() or None
            if not collection_name and tester_settings:
                collection_name = (tester_settings.get("rag_collection") or "").strip() or None
            if not collection_name:
                collection_name = (settings_repo.get_app_setting(RAG_COLLECTION_APP_SETTING) or "").strip() or None
            prompt_name = (prompt_name or "").strip() if isinstance(prompt_name, str) else str(prompt_name or "").strip()
            model_req = (str(model).strip() if model is not None else "")
            if not bool(use_rag):
                webui_dir = str(webui_data_dir()) if webui_data_dir().is_dir() else None
                params, deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=collection_name)
                use_model = model_req or (params.model_name if params else "")
                use_model = (str(use_model or "")).strip()
                if not use_model:
                    return _error_response("model is required", 400)
                options: dict[str, Any] = {}
                if temperature is not None:
                    try:
                        options["temperature"] = float(temperature)
                    except (TypeError, ValueError):
                        pass
                if top_p is not None:
                    try:
                        options["top_p"] = float(top_p)
                    except (TypeError, ValueError):
                        pass
                svc = get_extensions_service(current_app)
                runtime = get_extensions_runtime(current_app, svc)
                if runtime is not None and provider_id:
                    from llm_interactor.contracts import LLMRequest

                    resp = runtime.invoke(
                        LLMRequest(
                            provider_id=provider_id or default_llm_provider_id(),
                            model=use_model,
                            operation="chat",
                            messages=[m for m in messages if isinstance(m, dict)],
                            stream=False,
                            options=(options or None),
                        )
                    )
                    content = resp.text or ""
                else:
                    content = deps.chat_client.chat(messages, use_model, stream=False, options=(options or None)) or ""
                return jsonify(
                    {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": use_model,
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": content},
                                "finish_reason": "stop",
                            }
                        ],
                        "latency_ms": int((time.time() - start_time) * 1000),
                    }
                )

            proxy_body: dict[str, Any] = {
                "messages": messages,
                "stream": False,
                "include_rag_metadata": bool(use_rag),
                "skip_rag": (not bool(use_rag)),
                "fetch_web_knowledge": bool(fetch_web_knowledge),
            }
            if model_req:
                proxy_body["model"] = model_req
            if provider_id:
                proxy_body["provider_id"] = provider_id
            if collection_name:
                proxy_body["collection_name"] = collection_name
            if prompt_name:
                proxy_body["prompt_name"] = prompt_name
            if temperature is not None:
                proxy_body["temperature"] = temperature
            if top_p is not None:
                proxy_body["top_p"] = top_p
            if reasoning_level:
                proxy_body["reasoning_level"] = reasoning_level
            return run_unified_proxy_chat(proxy_body)

        except Exception as e:
            error_log.error("webui_model_tester_routes.tester_chat", exc_info=True)
            return _error_response(e)

    @bp.route("/tester/prompt-preview", methods=["POST"])
    def tester_prompt_preview() -> Any:
        """Return a preview of the full prompt that will be sent from Model Tester."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            prompt_name = (body.get("prompt_name") or "").strip() or get_rag_prompt_name()
            user_message = body.get("user_message") or ""
            use_rag = bool(body.get("use_rag", True))

            prefix, suffix = get_rag_system_prompt(prompt_name)

            try:
                confidence_threshold = get_rag_float("confidence_threshold", 0.75)
            except Exception:
                confidence_threshold = 0.75
            try:
                model_name = config_default_chat_model()
            except Exception:
                model_name = ""

            if use_rag:
                context_block = (
                    "<<RAG CONTEXT (retrieved documentation snippets) WILL BE INSERTED HERE>>"
                )
            else:
                context_block = "<<RAG IS DISABLED — no context snippets will be added>>"

            system_full = build_system_content(
                prefix or "",
                suffix or "",
                context_block,
                confidence_threshold,
                confidence_threshold,
                None,
                model_name or "",
            )

            preview_messages = [
                {"role": "system", "content": system_full},
                {
                    "role": "user",
                    "content": user_message or "<<your next chat message will be inserted here>>",
                },
            ]

            return jsonify(
                {
                    "prompt_name": prompt_name,
                    "system_prompt": prefix or "",
                    "system_message_full": system_full,
                    "preview_messages": preview_messages,
                }
            )
        except Exception as e:
            error_log.error("webui_model_tester_routes.tester_prompt_preview", exc_info=True)
            return _error_response(e)
