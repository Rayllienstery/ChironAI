"""LLM Proxy routes for WebUI (status, API keys, builds)."""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from typing import Any, Callable

from flask import Blueprint, current_app, jsonify, request

from error_manager.exceptions import ValidationError as _ValidationError
from error_manager.http import error_response as _error_response

from api.http.extensions_service_access import get_extensions_runtime, get_extensions_service
from application.llm_proxy_builds import (
    LLM_PROXY_BUILDS_APP_KEY,
    diagnose_build,
    dump_builds_json,
    extract_context_length_from_show,
    find_build_by_id,
    load_builds_json,
    validate_builds_list,
)
from llm_proxy.api_key import (
    delete_proxy_api_key_record,
    generate_proxy_api_key_record,
    proxy_api_key_status,
    reveal_proxy_api_key,
    store_proxy_api_key_record,
)
from config import (
    get_active_server_port,
    get_qdrant_url,
    get_server_host,
)
from config.rag_prompts import (
    rag_prompt_file_exists,
)
from infrastructure.database import (
    get_settings_repository,
)
from infrastructure.logging.webui_error_logger import get_webui_error_logger
import requests


_WEBUI_LOG = logging.getLogger("webui")
_ERROR_LOG = get_webui_error_logger()


_SERVICE_STATUS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SERVICE_STATUS_CACHE_LOCK = threading.Lock()
_LAST_QDRANT_WARN_AT: float = 0.0


def _webui_routes_attr(name: str) -> Any:
    parent = sys.modules.get("api.http.webui_routes")
    if parent is None:
        return None
    return getattr(parent, name, None)


def _settings_repository() -> Any:
    override = _webui_routes_attr("get_settings_repository")
    if callable(override):
        return override()
    return get_settings_repository()


def _get_cached_status(key: str, ttl_sec: float, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    now = time.time()
    with _SERVICE_STATUS_CACHE_LOCK:
        hit = _SERVICE_STATUS_CACHE.get(key)
        if hit is not None:
            ts, payload = hit
            if now - ts <= ttl_sec:
                return payload
    payload = compute()
    with _SERVICE_STATUS_CACHE_LOCK:
        _SERVICE_STATUS_CACHE[key] = (now, payload)
    return payload


def _qdrant_status_snapshot(timeout_sec: float) -> dict[str, Any]:
    url = get_qdrant_url().rstrip("/")
    status: dict[str, Any] = {"url": url, "running": False}
    try:
        resp = requests.get(f"{url}/collections", timeout=timeout_sec)
        status["http_status"] = resp.status_code
        if resp.ok:
            data = resp.json() or {}
            collections = data.get("result", {}).get("collections", [])
            status["running"] = True
            status["collections_count"] = len(collections)
            try:
                version_resp = requests.get(f"{url}/cluster", timeout=timeout_sec)
                if version_resp.ok:
                    vdata = version_resp.json() or {}
                    status["version"] = (
                        vdata.get("result", {})
                        .get("status", {})
                        .get("version")
                    )
            except Exception:
                pass
    except Exception as e:
        status["error"] = str(e)
        global _LAST_QDRANT_WARN_AT
        now = time.time()
        if now - _LAST_QDRANT_WARN_AT >= 30:
            _LAST_QDRANT_WARN_AT = now
            _WEBUI_LOG.warning("Failed to get Qdrant status: %s", e)
    return status


def _get_qdrant_collection_names() -> list[str]:
    """Return list of Qdrant collection names (empty if Qdrant unreachable or no collections)."""
    return _get_qdrant_collection_names_with_timeout(timeout_sec=5.0)


def _get_cached_qdrant_collection_name_set_for_builds_diag() -> set[str]:
    cache_key = f"llm_proxy_builds_diag_qdrant_names:{get_qdrant_url().rstrip('/')}"
    cached = _get_cached_status(
        cache_key,
        ttl_sec=3.0,
        compute=lambda: {"names": _get_qdrant_collection_names_with_timeout(timeout_sec=0.8)},
    )
    return set(cached.get("names") or [])


def _get_qdrant_collection_names_with_timeout(timeout_sec: float) -> list[str]:
    """Return Qdrant collection names using an explicit timeout."""
    url = get_qdrant_url().rstrip("/")
    try:
        resp = requests.get(f"{url}/collections", timeout=timeout_sec)
        if not resp.ok:
            return []
        data = resp.json() or {}
        raw = data.get("result", {}).get("collections", []) if isinstance(data, dict) else []
        names: list[str] = []
        for col in raw:
            if isinstance(col, dict):
                name = col.get("name")
            else:
                name = str(col)
            if name:
                names.append(name)
        return names
    except Exception:
        return []


def _default_llm_provider_id() -> str:
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


def _provider_catalog_payload(*, capability: str | None = None) -> dict[str, Any]:
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
    if svc is None:
        return {"providers": [], "models": []}
    try:
        return svc.provider_catalog(runtime=runtime, capability=capability)
    except Exception:
        return {"providers": [], "models": []}


def _provider_row(provider_id: str | None = None) -> dict[str, Any] | None:
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
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
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
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
    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
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


def _invoke_runtime_embed(
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
    if hasattr(response, "embeddings"):
        return response.embeddings
    return []


def register_llm_proxy_routes(
    bp: Blueprint,
    *,
    error_log: Any,
) -> None:
    """Register LLM Proxy routes on the given Blueprint."""

    @bp.route("/llm-proxy/status", methods=["GET"])
    def llm_proxy_status() -> Any:
        """Base URL for WebUI RAG Fusion Proxy Status card (per-build Ollama tags live on builds, not here)."""
        try:
            bind_host = get_server_host()
            display_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
            port = get_active_server_port()
            base_url = f"http://{display_host}:{port}"
            payload: dict[str, Any] = {
                "enabled": True,
                "base_url": base_url,
                "health": f"{base_url}/health",
            }
            return jsonify(payload)
        except Exception as e:
            error_log.error("webui_llm_proxy_routes.llm_proxy_status", exc_info=True)
            return _error_response(e)

    @bp.route("/ollama/status", methods=["GET"])
    def ollama_provider_status() -> Any:
        """Compatibility status endpoint backed by the default provider extension."""
        try:
            row = _default_provider_row()
            if row is None:
                return jsonify({"running": False, "error": "No default provider extension loaded"}), 503
            health = row.get("health") if isinstance(row.get("health"), dict) else {}
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            details = health.get("details") if isinstance(health.get("details"), dict) else {}
            return jsonify(
                {
                    "url": metadata.get("base_url") or metadata.get("chat_url") or None,
                    "running": bool(health.get("ok")),
                    "http_status": details.get("status_code"),
                    "error": health.get("message") or "",
                }
            )
        except Exception as e:
            error_log.error("webui_llm_proxy_routes.ollama_provider_status", exc_info=True)
            return _error_response(e)

    @bp.route("/ollama/start", methods=["POST"])
    def ollama_provider_start() -> Any:
        """Compatibility start endpoint backed by the default provider extension."""
        try:
            payload = request.get_json(silent=True) or {}
            result = _run_default_provider_extension_action("start_service", payload if isinstance(payload, dict) else {})
            status = 200 if bool(result.get("ok")) else 500
            return jsonify({"ok": bool(result.get("ok")), "output": result.get("message") or ""}), status
        except Exception:
            error_log.error("webui_llm_proxy_routes.ollama_provider_start", exc_info=True)
            return jsonify({"ok": False, "output": "Provider extension start failed.", "code": "provider_start_failed"}), 500

    @bp.route("/ollama/stop", methods=["POST"])
    def ollama_provider_stop() -> Any:
        """Compatibility stop endpoint backed by the default provider extension."""
        try:
            payload = request.get_json(silent=True) or {}
            result = _run_default_provider_extension_action("stop_service", payload if isinstance(payload, dict) else {})
            status = 200 if bool(result.get("ok")) else 500
            return jsonify({"ok": bool(result.get("ok")), "output": result.get("message") or ""}), status
        except Exception:
            error_log.error("webui_llm_proxy_routes.ollama_provider_stop", exc_info=True)
            return jsonify({"ok": False, "output": "Provider extension stop failed.", "code": "provider_stop_failed"}), 500

    @bp.route("/llm-proxy/api-key", methods=["GET"])
    def llm_proxy_api_key_status() -> Any:
        """Return public metadata for the WebUI-managed Chiron /v1 API key."""
        try:
            return jsonify(proxy_api_key_status(_settings_repository()))
        except Exception as e:
            error_log.error("webui_llm_proxy_routes.llm_proxy_api_key_status", exc_info=True)
            return _error_response(e)

    @bp.route("/llm-proxy/api-key/generate", methods=["POST"])
    def llm_proxy_generate_api_key() -> Any:
        """Create or rotate the Chiron /v1 API key. Plaintext is returned only here."""
        try:
            settings_repo = _settings_repository()
            plaintext, record = generate_proxy_api_key_record(settings_repo)
            store_proxy_api_key_record(settings_repo, record)
            payload = {
                "key": plaintext,
                **proxy_api_key_status(settings_repo),
            }
            return jsonify(payload)
        except Exception as e:
            error_log.error("webui_llm_proxy_routes.llm_proxy_generate_api_key", exc_info=True)
            return _error_response(e)

    @bp.route("/llm-proxy/api-key/reveal", methods=["POST"])
    def llm_proxy_reveal_api_key() -> Any:
        """Return the recoverable Chiron /v1 API key for WebUI admin reuse."""
        try:
            settings_repo = _settings_repository()
            plaintext = reveal_proxy_api_key(settings_repo)
            if not plaintext:
                return _error_response("Chiron proxy API key is not recoverable", 404)
            return jsonify({"key": plaintext, **proxy_api_key_status(settings_repo)})
        except Exception as e:
            error_log.error("webui_llm_proxy_routes.llm_proxy_reveal_api_key", exc_info=True)
            return _error_response(e)

    @bp.route("/llm-proxy/api-key", methods=["DELETE"])
    def llm_proxy_delete_api_key() -> Any:
        """Delete the Chiron /v1 API key and close protected routes until regenerated."""
        try:
            settings_repo = _settings_repository()
            delete_proxy_api_key_record(settings_repo)
            return jsonify(proxy_api_key_status(settings_repo))
        except Exception as e:
            error_log.error("webui_llm_proxy_routes.llm_proxy_delete_api_key", exc_info=True)
            return _error_response(e)

    def _ollama_tag_name_set_for_builds_diag() -> set[str]:
        svc = get_extensions_service(current_app)
        runtime = get_extensions_runtime(current_app, svc)
        cache_key = f"llm_proxy_builds_diag_provider_catalog_ollama_names:{id(svc)}:{id(runtime)}"
        cached = _get_cached_status(
            cache_key,
            ttl_sec=3.0,
            compute=lambda: {"names": sorted(_provider_catalog_model_name_set_for_builds_diag())},
        )
        return set(cached.get("names") or [])

    def _provider_catalog_model_name_set_for_builds_diag() -> set[str]:
        names: set[str] = set()
        try:
            catalog = _provider_catalog_payload(capability="chat")
            for model in catalog.get("models") or []:
                if not isinstance(model, dict):
                    continue
                provider_id = str(model.get("provider_id") or "").strip()
                if provider_id != "ollama":
                    continue
                for key in ("id", "name", "label"):
                    value = str(model.get(key) or "").strip()
                    if value:
                        names.add(value)
        except Exception:
            pass
        return names

    def _enrich_builds_with_diagnostics(builds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from concurrent.futures import ThreadPoolExecutor

        ollama_names = _ollama_tag_name_set_for_builds_diag()
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_q = pool.submit(_get_cached_qdrant_collection_name_set_for_builds_diag)
            qset = fut_q.result()
        out: list[dict[str, Any]] = []
        for b in builds:
            row = dict(b)
            row["use_prompt_template"] = b.get("use_prompt_template", True) is not False
            issues, healthy = diagnose_build(
                b,
                ollama_tag_names=ollama_names,
                prompt_exists=rag_prompt_file_exists(str(b.get("prompt_name") or "").strip()),
                qdrant_collection_names=qset,
            )
            row["issues"] = issues
            row["healthy"] = healthy
            out.append(row)
        return out

    def _light_build_rows_for_webui(builds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Same shape as enriched builds but without Ollama/Qdrant/prompt diagnostics (fast first paint)."""
        out: list[dict[str, Any]] = []
        for b in builds:
            row = dict(b)
            row["use_prompt_template"] = b.get("use_prompt_template", True) is not False
            row["issues"] = []
            row["healthy"] = True
            out.append(row)
        return out

    def _enrich_builds_with_diagnostics_for_webui_routes(builds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        override = _webui_routes_attr("_enrich_builds_with_diagnostics")
        if callable(override):
            return override(builds)
        return _enrich_builds_with_diagnostics(builds)

    @bp.route("/llm-proxy/builds", methods=["GET"])
    def get_llm_proxy_builds() -> Any:
        """List LLM Proxy builds with validation hints for WebUI."""
        try:
            settings_repo = _settings_repository()
            raw = settings_repo.get_app_setting(LLM_PROXY_BUILDS_APP_KEY)
            builds = load_builds_json(raw)
            diag_raw = (request.args.get("diagnostics") or "1").strip().lower()
            include_diagnostics = diag_raw not in ("0", "false", "no", "off")
            if include_diagnostics:
                enriched = _enrich_builds_with_diagnostics_for_webui_routes(builds)
            else:
                enriched = _light_build_rows_for_webui(builds)
            sh = get_server_host()
            dh = "127.0.0.1" if sh in ("0.0.0.0", "::", "") else sh
            main_port = get_active_server_port()
            return jsonify(
                {
                    "builds": enriched,
                    "openai_models_urls": {
                        "main": f"http://{dh}:{main_port}/v1/models",
                    },
                }
            )
        except Exception as e:
            error_log.error("webui_llm_proxy_routes.get_llm_proxy_builds", exc_info=True)
            return _error_response(e)

    @bp.route("/llm-proxy/builds", methods=["PUT"])
    def put_llm_proxy_builds() -> Any:
        """Replace full builds list (atomic validation)."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            raw_list = body.get("builds")
            if not isinstance(raw_list, list):
                return _error_response("builds must be a JSON array", 400)
            normalized, errs = validate_builds_list([x for x in raw_list if isinstance(x, dict)])
            if normalized is None:
                return _error_response(_ValidationError("validation failed", details=errs))
            settings_repo = _settings_repository()
            settings_repo.set_app_setting(LLM_PROXY_BUILDS_APP_KEY, dump_builds_json(normalized))
            enriched = _enrich_builds_with_diagnostics_for_webui_routes(normalized)
            return jsonify({"ok": True, "builds": enriched})
        except Exception as e:
            error_log.error("webui_llm_proxy_routes.put_llm_proxy_builds", exc_info=True)
            return _error_response(e)

    @bp.route("/llm-proxy/builds/<build_id>", methods=["GET"])
    def get_llm_proxy_build_one(build_id: str) -> Any:
        """Single build by id with diagnostics."""
        try:
            if ".." in build_id or "/" in build_id or "\\" in build_id:
                return _error_response("Invalid id", 400)
            settings_repo = _settings_repository()
            raw = settings_repo.get_app_setting(LLM_PROXY_BUILDS_APP_KEY)
            builds = load_builds_json(raw)
            b = find_build_by_id(builds, build_id)
            if not b:
                return _error_response("not found", 404)
            enriched = _enrich_builds_with_diagnostics_for_webui_routes([b])[0]
            return jsonify({"build": enriched})
        except Exception as e:
            error_log.error("webui_llm_proxy_routes.get_llm_proxy_build_one", exc_info=True)
            return _error_response(e)

    @bp.route("/llm-proxy/builds/preview-model", methods=["POST"])
    def llm_proxy_build_preview_model() -> Any:
        """Ollama show: context_length + thinking support for form helpers."""
        body = request.get_json(force=True, silent=True) or {}
        provider_id = str(body.get("provider_id") or "").strip() or _default_llm_provider_id()
        model = (body.get("model") or "").strip()
        if not model:
            return jsonify({"ok": False, "error": "model is required"}), 400
        try:
            result = _run_provider_extension_action(provider_id, "show_model", {"selected_model": model})
            details = result.get("details") if isinstance(result, dict) else {}
        except Exception:
            error_log.error("webui_llm_proxy_routes.llm_proxy_build_preview_model", exc_info=True)
            return jsonify({"ok": False, "error": "provider extension preview failed.", "code": "provider_preview_failed"}), 502
        ctx_len = extract_context_length_from_show(details if isinstance(details, dict) else None)
        caps = None
        if isinstance(details, dict):
            c = details.get("capabilities")
            if isinstance(c, list):
                caps = [str(x).strip().lower() for x in c if isinstance(x, str)]
        thinking = False
        if caps:
            thinking = "thinking" in caps or "think" in caps
        return jsonify(
            {
                "ok": True,
                "context_length": ctx_len,
                "supports_thinking": thinking,
                "capabilities": caps or [],
            }
        )
