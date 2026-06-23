"""RAG settings, pipeline diagram, and Qdrant operations for the WebUI blueprint."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import threading
import time
from typing import Any, Callable

import requests
from chironai_rag.consumers import RAG_COLLECTION_APP_SETTING
from error_manager.http import error_response as _error_response
from flask import Blueprint, jsonify, request
from rag_service.domain.services.rag_trigger import compute_rag_trigger_score

from api.http.proxy_status import (
    get_latest_request_rag_steps,
    get_latest_request_seconds,
    get_latest_request_total_tokens,
    get_proxy_status_label,
)
from api.http.proxy_trace import get_current_trace
from api.http.rag_sources_meta import (
    clear_chunk_hashes_for_sources,
    parse_source_ids_from_framework_id,
)
from api.http.service_control import (
    start_qdrant as start_qdrant_service,
)
from api.http.service_control import (
    stop_qdrant as stop_qdrant_service,
)
from api.http.webui_crawler_helpers import is_safe_identifier
from application.rag.proxy_settings_contract import (
    load_proxy_settings,
    resolve_hybrid_sparse_enabled,
    resolve_web_interaction_flags,
)
from config import get_default_rag_top_k, get_framework_collection_ttl_days, get_qdrant_url, get_retrieval_bool
from infrastructure.database import get_settings_repository
from infrastructure.qdrant.collection_names import list_collection_names

_WEBUI_LOG = logging.getLogger("webui")

_SERVICE_STATUS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SERVICE_STATUS_CACHE_LOCK = threading.Lock()
_LAST_QDRANT_WARN_AT: float = 0.0


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


def _collection_is_stale(last_refreshed_at: str | None, ttl_days: int) -> bool:
    if not last_refreshed_at or ttl_days <= 0:
        return False
    try:
        from datetime import datetime, timezone

        raw = str(last_refreshed_at).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        refreshed = datetime.fromisoformat(raw)
        if refreshed.tzinfo is None:
            refreshed = refreshed.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - refreshed).total_seconds() / 86400.0
        return age_days > float(ttl_days)
    except Exception:  # safe: invalid coercion defaults to disabled
        return False


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
            except Exception:  # safe: Qdrant cluster version probe is optional
                pass
    except Exception as e:
        status["error"] = str(e)
        global _LAST_QDRANT_WARN_AT
        now = time.time()
        if now - _LAST_QDRANT_WARN_AT >= 30:
            _LAST_QDRANT_WARN_AT = now
            _WEBUI_LOG.warning("Failed to get Qdrant status: %s", e)
    return status


def get_qdrant_collection_names_with_timeout(timeout_sec: float) -> list[str]:
    return list_collection_names(timeout_sec=timeout_sec)


def get_qdrant_collection_names() -> list[str]:
    """Return Qdrant collection names (empty if unreachable)."""
    return list_collection_names(timeout_sec=5.0)


def get_cached_qdrant_collection_name_set_for_builds_diag() -> set[str]:
    cache_key = f"llm_proxy_builds_diag_qdrant_names:{get_qdrant_url().rstrip('/')}"
    cached = _get_cached_status(
        cache_key,
        ttl_sec=3.0,
        compute=lambda: {"names": get_qdrant_collection_names_with_timeout(timeout_sec=0.8)},
    )
    return set(cached.get("names") or [])


def _get_gpu_metrics() -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0 or not result.stdout or not result.stdout.strip():
            return None
        line = result.stdout.strip().split("\n")[0].strip()
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            return None

        def _int_or_none(s: str) -> int | None:
            s = (s or "").strip()
            return int(s) if s.isdigit() else None

        util_s = (parts[0] or "").replace("%", "").strip()
        mem_used = (parts[1] or "").replace("MiB", "").replace("MB", "").strip()
        mem_total = (parts[2] or "").replace("MiB", "").replace("MB", "").strip()
        temp_s = (parts[3] or "").replace("C", "").strip() if len(parts) > 3 else ""
        return {
            "utilization_pct": _int_or_none(util_s),
            "memory_used_mb": _int_or_none(mem_used),
            "memory_total_mb": _int_or_none(mem_total),
            "temperature_c": _int_or_none(temp_s),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


def _retrieval_yaml_raw_bool(key: str) -> bool:
    try:
        from config import RETRIEVAL_CONFIG

        v = RETRIEVAL_CONFIG.get(key, False)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(v, (int, float)):
            return bool(v)
        return bool(v)
    except Exception:  # safe: invalid coercion defaults to disabled
        return False


def _get_rag_pipeline_definition_payload() -> list[dict[str, Any]]:
    try:
        from rag_service.application import get_rag_pipeline_definition

        steps = get_rag_pipeline_definition()
        if isinstance(steps, list):
            return [dict(s) for s in steps if isinstance(s, dict)]
    except Exception:  # safe: pipeline definition optional when rag_service unavailable
        pass
    return []


def _get_proxy_pipeline_definition_payload() -> list[dict[str, Any]]:
    try:
        from llm_proxy.pipeline_steps import get_proxy_pipeline_definition

        steps = get_proxy_pipeline_definition()
        if isinstance(steps, list):
            return [dict(s) for s in steps if isinstance(s, dict)]
    except Exception:  # safe: pipeline definition optional when rag_service unavailable
        pass
    return []


def _get_proxy_last_executed_steps_payload() -> list[dict[str, Any]]:
    trace = get_current_trace()
    if not isinstance(trace, dict):
        return []
    raw = trace.get("pipeline_steps")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        if not sid:
            continue
        out.append(
            {
                "id": sid,
                "status": str(item.get("status") or ""),
                "reason": item.get("reason"),
            }
        )
    return out


def _build_pipeline_definition_payload() -> dict[str, Any]:
    return {
        "rag": {"steps": _get_rag_pipeline_definition_payload()},
        "proxy": {"steps": _get_proxy_pipeline_definition_payload()},
    }


def register_rag_pipeline_routes(
    bp: Blueprint,
    *,
    error_log: Any,
    default_llm_provider_id: Callable[[], str],
    read_app_provider_model_ref: Callable[..., tuple[str, str]],
    config_default_embed_model: Callable[[], str],
    config_default_rerank_model: Callable[[], str],
    get_effective_rag_trigger_threshold: Callable[[], int],
    get_rag_required_keywords_from_module: Callable[[], list[str] | None],
) -> None:
    def _read_dict_provider_model_ref(
        blob: dict[str, Any],
        *,
        provider_key: str,
        model_key: str,
        fallback_provider: str | None = None,
    ) -> tuple[str, str]:
        provider_id = str(blob.get(provider_key) or "").strip()
        model = str(blob.get(model_key) or "").strip()
        if model and not provider_id:
            provider_id = str(fallback_provider or default_llm_provider_id()).strip()
        return provider_id, model

    @bp.route("/rag-model-settings", methods=["GET"])
    def get_rag_model_settings() -> Any:
        try:
            from application.rag.retrieval_ui_overrides import RETRIEVAL_UI_BOOL_KEYS, retrieval_bool_with_ui_override

            settings_repo = get_settings_repository()
            default_provider_id = default_llm_provider_id()
            default_embed_model = config_default_embed_model()
            default_rerank_model = config_default_rerank_model()

            rag_embed_provider_id, rag_embed_model = read_app_provider_model_ref(
                settings_repo,
                provider_key="rag_embed_provider_id",
                model_key="rag_embed_model",
                fallback_provider=default_provider_id,
            )
            proxy_settings = load_proxy_settings(settings_repo)
            rerank_for_rag = bool(proxy_settings.get("rerank_for_rag", False))
            rag_rerank_provider_id, raw_rerank_model = _read_dict_provider_model_ref(
                proxy_settings,
                provider_key="rag_rerank_provider_id",
                model_key="rerank_model",
                fallback_provider=default_provider_id,
            )
            rerank_model = raw_rerank_model if raw_rerank_model else (default_rerank_model if rerank_for_rag else "")
            if rerank_model and not rag_rerank_provider_id:
                rag_rerank_provider_id = default_provider_id

            yaml_hybrid = get_retrieval_bool("hybrid_sparse_enabled", True)
            hybrid_sparse_enabled, hybrid_source = resolve_hybrid_sparse_enabled(
                proxy_settings=proxy_settings,
                yaml_default=yaml_hybrid,
            )
            retrieval_advanced = {k: retrieval_bool_with_ui_override(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}
            retrieval_yaml_defaults = {k: _retrieval_yaml_raw_bool(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}

            return jsonify(
                {
                    "rag_embed_provider_id": rag_embed_provider_id,
                    "rag_embed_model": rag_embed_model,
                    "rag_rerank_provider_id": rag_rerank_provider_id,
                    "rerank_for_rag": rerank_for_rag,
                    "rerank_model": rerank_model,
                    "hybrid_sparse_enabled": hybrid_sparse_enabled,
                    "retrieval_advanced": retrieval_advanced,
                    "retrieval_yaml_defaults": retrieval_yaml_defaults,
                    "defaults": {
                        "rag_embed_provider_id": default_provider_id,
                        "rag_embed_model": default_embed_model,
                        "rag_rerank_provider_id": default_provider_id,
                        "rerank_model": default_rerank_model,
                        "hybrid_sparse_enabled": yaml_hybrid,
                    },
                    "contract_sources": {
                        "hybrid_sparse_enabled": hybrid_source,
                        "rerank_for_rag": (
                            "proxy_settings.rerank_for_rag" if "rerank_for_rag" in proxy_settings else "default.false"
                        ),
                    },
                    "pipeline_definition": {
                        "rag": {"steps": _get_rag_pipeline_definition_payload()},
                    },
                }
            )
        except Exception as e:
            error_log.error("webui_rag_routes.get_rag_model_settings", exc_info=True)
            return _error_response(e)

    @bp.route("/rag-model-settings", methods=["POST"])
    def update_rag_model_settings() -> Any:
        try:
            from application.rag.retrieval_ui_overrides import RETRIEVAL_UI_BOOL_KEYS, retrieval_bool_with_ui_override

            body = request.get_json(force=True, silent=True) or {}
            settings_repo = get_settings_repository()
            default_provider_id = default_llm_provider_id()
            default_rerank_model = config_default_rerank_model()

            rag_embed_provider_id = str(body.get("rag_embed_provider_id") or "").strip() or default_provider_id
            rag_embed_model = str(body.get("rag_embed_model") or "").strip()
            settings_repo.set_app_setting("rag_embed_provider_id", rag_embed_provider_id)
            settings_repo.set_app_setting("rag_embed_model", rag_embed_model)

            rag_rerank_provider_id = str(body.get("rag_rerank_provider_id") or "").strip() or default_provider_id
            rerank_for_rag = bool(body.get("rerank_for_rag", False))
            rerank_model = str(body.get("rerank_model") or "").strip()
            yaml_hybrid = get_retrieval_bool("hybrid_sparse_enabled", True)
            hybrid_sparse_enabled = bool(body.get("hybrid_sparse_enabled", yaml_hybrid))

            proxy_settings = dict(load_proxy_settings(settings_repo))

            proxy_settings["rerank_for_rag"] = rerank_for_rag
            proxy_settings["hybrid_sparse_enabled"] = hybrid_sparse_enabled
            proxy_settings["rag_rerank_provider_id"] = rag_rerank_provider_id

            for rk in RETRIEVAL_UI_BOOL_KEYS:
                if rk in body:
                    proxy_settings[rk] = bool(body.get(rk))

            if rerank_for_rag:
                proxy_settings["rerank_model"] = rerank_model or default_rerank_model
            elif rerank_model:
                proxy_settings["rerank_model"] = rerank_model

            settings_repo.set_app_setting("proxy_settings", json.dumps(proxy_settings))

            default_embed_model = config_default_embed_model()
            retrieval_advanced = {k: retrieval_bool_with_ui_override(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}
            retrieval_yaml_defaults = {k: _retrieval_yaml_raw_bool(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}
            return jsonify(
                {
                    "status": "ok",
                    "rag_embed_provider_id": rag_embed_provider_id,
                    "rag_embed_model": rag_embed_model,
                    "rag_rerank_provider_id": rag_rerank_provider_id,
                    "rerank_for_rag": rerank_for_rag,
                    "rerank_model": proxy_settings.get("rerank_model") or "",
                    "hybrid_sparse_enabled": hybrid_sparse_enabled,
                    "retrieval_advanced": retrieval_advanced,
                    "retrieval_yaml_defaults": retrieval_yaml_defaults,
                    "defaults": {
                        "rag_embed_provider_id": default_provider_id,
                        "rag_embed_model": default_embed_model,
                        "rag_rerank_provider_id": default_provider_id,
                        "rerank_model": default_rerank_model,
                        "hybrid_sparse_enabled": yaml_hybrid,
                    },
                }
            )
        except Exception as e:
            error_log.error("webui_rag_routes.update_rag_model_settings", exc_info=True)
            return _error_response(e)

    @bp.route("/pipeline-preview", methods=["GET"])
    def get_pipeline_preview() -> Any:
        try:
            settings_repo = get_settings_repository()
            rag_col = (settings_repo.get_app_setting(RAG_COLLECTION_APP_SETTING) or "").strip()
            rag_collection_configured = bool(rag_col)
            proxy_settings = load_proxy_settings(settings_repo)

            fetch_web_knowledge = bool(proxy_settings.get("fetch_web_knowledge", False))
            rerank_for_rag = bool(proxy_settings.get("rerank_for_rag", False))
            yaml_hybrid = get_retrieval_bool("hybrid_sparse_enabled", True)
            hybrid_sparse_enabled, hybrid_source = resolve_hybrid_sparse_enabled(
                proxy_settings=proxy_settings,
                yaml_default=yaml_hybrid,
            )

            raw_news = False
            raw_fetch = False
            raw_wiki = False
            global_web = True
            try:
                from web_interaction.config import ddg_news_enabled, web_interaction_globally_enabled
                from web_interaction.fetch_excerpt import fetch_page_env_enabled
                from web_interaction.wikipedia_fallback import wikipedia_env_enabled

                global_web = web_interaction_globally_enabled()
                raw_news = ddg_news_enabled()
                raw_fetch = fetch_page_env_enabled()
                raw_wiki = wikipedia_env_enabled()
            except ImportError:
                pass

            web_flags = resolve_web_interaction_flags(
                proxy_settings=proxy_settings,
                env_ddg_news=raw_news,
                env_fetch_page=raw_fetch,
                env_wikipedia=raw_wiki,
            )

            return jsonify(
                {
                    "rag_collection_configured": rag_collection_configured,
                    "hybrid_sparse_enabled": hybrid_sparse_enabled,
                    "rerank_for_rag": rerank_for_rag,
                    "fetch_web_knowledge": fetch_web_knowledge,
                    "web_interaction_enabled": bool(web_flags["web_interaction_enabled"]["value"]),
                    "web_interaction_on_keywords": bool(web_flags["web_interaction_on_keywords"]["value"]),
                    "web_interaction_on_low_confidence_framework": bool(
                        web_flags["web_interaction_on_low_confidence_framework"]["value"]
                    ),
                    "env": {
                        "web_interaction_globally_enabled": global_web,
                        "ddg_news": bool(web_flags["web_interaction_ddg_news"]["value"]),
                        "fetch_page": bool(web_flags["web_interaction_fetch_page"]["value"]),
                        "wikipedia": bool(web_flags["web_interaction_wikipedia"]["value"]),
                    },
                    "env_raw": {
                        "ddg_news": raw_news,
                        "fetch_page": raw_fetch,
                        "wikipedia": raw_wiki,
                    },
                    "contract_sources": {
                        "hybrid_sparse_enabled": hybrid_source,
                        "web_interaction_enabled": str(web_flags["web_interaction_enabled"]["source"]),
                        "web_interaction_on_keywords": str(web_flags["web_interaction_on_keywords"]["source"]),
                        "web_interaction_on_low_confidence_framework": str(
                            web_flags["web_interaction_on_low_confidence_framework"]["source"]
                        ),
                        "web_interaction_ddg_news": str(web_flags["web_interaction_ddg_news"]["source"]),
                        "web_interaction_fetch_page": str(web_flags["web_interaction_fetch_page"]["source"]),
                        "web_interaction_wikipedia": str(web_flags["web_interaction_wikipedia"]["source"]),
                    },
                    "pipeline_definition": _build_pipeline_definition_payload(),
                    "proxy_last_executed_steps": _get_proxy_last_executed_steps_payload(),
                }
            )
        except Exception as e:
            error_log.error("webui_rag_routes.get_pipeline_preview", exc_info=True)
            return _error_response(e)

    @bp.route("/pipeline-definition", methods=["GET"])
    def get_pipeline_definition() -> Any:
        try:
            return jsonify(
                {
                    "pipeline_definition": _build_pipeline_definition_payload(),
                    "proxy_last_executed_steps": _get_proxy_last_executed_steps_payload(),
                }
            )
        except Exception as e:
            error_log.error("webui_rag_routes.get_pipeline_definition", exc_info=True)
            return _error_response(e)

    @bp.route("/rag-trigger-test", methods=["POST"])
    def rag_trigger_test() -> Any:
        try:
            body = request.get_json(force=True, silent=True) or {}
            message = (body.get("message") or "").strip()
            threshold = get_effective_rag_trigger_threshold()
            rag_keywords = get_rag_required_keywords_from_module()
            score, signals, triggered = compute_rag_trigger_score(
                message,
                rag_required_keywords=rag_keywords,
                trigger_threshold=threshold,
            )
            return jsonify({
                "score": score,
                "signals": signals,
                "triggered": triggered,
                "threshold": threshold,
            })
        except Exception as e:
            error_log.error("webui_rag_routes.rag_trigger_test", exc_info=True)
            return _error_response(e)


def register_rag_qdrant_routes(
    bp: Blueprint,
    *,
    error_log: Any,
    default_provider_row: Callable[[], dict[str, Any] | None],
) -> None:
    @bp.route("/rag/status", methods=["GET"])
    def rag_status() -> Any:
        status = _get_cached_status(
            "qdrant_status",
            ttl_sec=2.0,
            compute=lambda: _qdrant_status_snapshot(timeout_sec=0.6),
        )
        return jsonify(status)

    @bp.route("/dashboard-metrics", methods=["GET"])
    def dashboard_metrics() -> Any:
        payload: dict[str, Any] = {"rag": {}, "ollama": {}, "gpu": None}
        q = _get_cached_status(
            "qdrant_status",
            ttl_sec=2.0,
            compute=lambda: _qdrant_status_snapshot(timeout_sec=0.6),
        )
        payload["rag"] = {
            "running": bool(q.get("running")),
            "collections_count": int(q.get("collections_count") or 0),
        }
        provider_row = default_provider_row()
        provider_health = provider_row.get("health") if isinstance(provider_row, dict) else None
        payload["ollama"] = {
            "running": bool(provider_health.get("ok")) if isinstance(provider_health, dict) else False
        }
        payload["gpu"] = _get_gpu_metrics()
        payload["proxy_status"] = get_proxy_status_label()
        payload["latest_request_seconds"] = get_latest_request_seconds()
        payload["latest_request_total_tokens"] = get_latest_request_total_tokens()
        payload["latest_request_rag_steps"] = get_latest_request_rag_steps()
        return jsonify(payload)

    @bp.route("/rag/collections", methods=["GET"])
    def rag_collections() -> Any:
        url = get_qdrant_url().rstrip("/")
        ttl_days = get_framework_collection_ttl_days()
        default_top_k = get_default_rag_top_k()
        try:
            settings_repo = get_settings_repository()
            ttl_raw = settings_repo.get_app_setting("framework_collection_ttl_days")
            if ttl_raw is not None and str(ttl_raw).strip() != "":
                with contextlib.suppress(TypeError, ValueError):
                    ttl_days = int(ttl_raw)
            top_k_raw = settings_repo.get_app_setting("default_rag_top_k")
            if top_k_raw is not None and str(top_k_raw).strip() != "":
                with contextlib.suppress(TypeError, ValueError):
                    default_top_k = int(top_k_raw)
        except Exception:  # safe: settings repository optional for RAG defaults
            pass

        try:
            resp = requests.get(f"{url}/collections", timeout=5)
        except requests.exceptions.RequestException as e:
            _WEBUI_LOG.warning("Qdrant unreachable at %s: %s", url, e)
            return jsonify({
                "collections": [],
                "error": "qdrant_unreachable",
                "ttl_days": ttl_days,
                "default_rag_top_k": default_top_k,
            })

        try:
            if not resp.ok:
                _WEBUI_LOG.warning("Qdrant /collections returned %s: %s", resp.status_code, resp.text)
                return jsonify({"collections": [], "error": f"HTTP {resp.status_code}"}), resp.status_code
            data = resp.json() or {}

            raw_collections = data.get("result", {}).get("collections", []) if isinstance(data, dict) else []
            names: list[str] = []
            for col in raw_collections:
                name = col.get("name") if isinstance(col, dict) else str(col)
                if name:
                    names.append(name)

            from qdrant_client import QdrantClient as _QdrantClient  # noqa: PLC0415

            client = _QdrantClient(url=url)
            detailed: list[dict[str, Any]] = []
            for name in names:
                try:
                    info = client.get_collection(name)
                    params = getattr(getattr(info, "config", None), "params", None)
                    points_count = getattr(info, "points_count", None)
                    shards_count = getattr(params, "shard_number", None) if params else None
                    replication_factor = getattr(params, "replication_factor", None) if params else None
                    on_disk = bool(getattr(params, "on_disk_payload", False)) if params else False
                    segments_count = getattr(info, "segments_count", None)
                    vectors_config = None
                    vectors_info = getattr(params, "vectors", None) if params else None
                    if vectors_info:
                        if isinstance(vectors_info, dict):
                            vector_name = "Default" if "Default" in vectors_info else next(iter(vectors_info.keys()), None)
                            if vector_name:
                                vec_params = vectors_info[vector_name]
                                if hasattr(vec_params, "size") and hasattr(vec_params, "distance"):
                                    vectors_config = {
                                        "name": vector_name,
                                        "size": vec_params.size,
                                        "distance": str(getattr(vec_params, "distance", "")).split(".")[-1]
                                        if hasattr(vec_params, "distance")
                                        else None,
                                    }
                        elif hasattr(vectors_info, "size") and hasattr(vectors_info, "distance"):
                            vectors_config = {
                                "name": "Default",
                                "size": vectors_info.size,
                                "distance": str(getattr(vectors_info, "distance", "")).split(".")[-1]
                                if hasattr(vectors_info, "distance")
                                else None,
                            }

                    item = {
                        "name": name,
                        "points_count": points_count,
                        "shards_count": shards_count,
                        "replication_factor": replication_factor,
                        "on_disk": on_disk,
                        "segments_count": segments_count,
                        "vectors_config": vectors_config,
                    }
                    try:
                        settings_repo = get_settings_repository()
                        meta = settings_repo.get_collection_meta(name)
                        if meta:
                            item["last_refreshed_at"] = meta.get("last_refreshed_at")
                            item["framework_id"] = meta.get("framework_id")
                            item["version"] = meta.get("version")
                            item["is_stale"] = _collection_is_stale(
                                meta.get("last_refreshed_at"), ttl_days
                            )
                        index_meta_raw = settings_repo.get_app_setting(
                            f"rag_collection_index_meta:{name}"
                        )
                        if index_meta_raw:
                            with contextlib.suppress(json.JSONDecodeError):
                                item["index_meta"] = json.loads(index_meta_raw)
                    except Exception:  # safe: per-collection enrichment failure skips optional fields
                        pass
                    detailed.append(item)
                except Exception as e:
                    _WEBUI_LOG.warning("Failed to get collection %s: %s", name, e)
                    detailed.append({"name": name})

            return jsonify({
                "collections": detailed,
                "ttl_days": ttl_days,
                "default_rag_top_k": default_top_k,
            })
        except Exception as e:
            _WEBUI_LOG.error("Failed to get Qdrant collections: %s", e, exc_info=True)
            return jsonify({
                "collections": [],
                "error": str(e),
                "ttl_days": ttl_days,
                "default_rag_top_k": default_top_k,
            }), 500

    @bp.route("/rag/collections/<collection_name>", methods=["DELETE"])
    def delete_rag_collection(collection_name: str) -> Any:
        """Delete a Qdrant collection and clear crawl index bookkeeping for its sources."""
        name = (collection_name or "").strip()
        if not name or not is_safe_identifier(name):
            return _error_response("Invalid collection name", 400)
        url = get_qdrant_url().rstrip("/")
        source_ids: list[str] = []
        settings_repo = get_settings_repository()
        try:
            meta = settings_repo.get_collection_meta(name)
            if meta:
                source_ids = parse_source_ids_from_framework_id(meta.get("framework_id"))
        except Exception:  # safe: collection meta lookup optional before delete
            pass
        try:
            resp = requests.delete(f"{url}/collections/{name}", timeout=10)
            if resp.status_code not in (200, 202, 404):
                return jsonify({
                    "error": f"Qdrant delete failed: HTTP {resp.status_code}",
                    "detail": resp.text[:500],
                }), resp.status_code
        except requests.exceptions.RequestException as e:
            return jsonify({"error": "qdrant_unreachable", "detail": str(e)}), 503
        cleared_pages = 0
        if source_ids:
            try:
                cleared_pages = clear_chunk_hashes_for_sources(source_ids)
            except Exception as e:
                _WEBUI_LOG.warning("Failed to clear chunk_hashes for %s: %s", name, e)
        if settings_repo is not None:
            try:
                settings_repo.delete_collection_meta(name)
                settings_repo.delete_app_setting(f"rag_collection_index_meta:{name}")
            except Exception:
                _WEBUI_LOG.warning("Failed to remove collection meta for %s", name, exc_info=True)
        return jsonify({
            "status": "ok",
            "collection_name": name,
            "cleared_chunk_hash_pages": cleared_pages,
            "source_ids": source_ids,
        })

    @bp.route("/rag/collection-settings", methods=["POST"])
    def save_rag_collection_settings() -> Any:
        try:
            body = request.get_json(force=True, silent=True) or {}
            settings_repo = get_settings_repository()
            if "ttl_days" in body:
                with contextlib.suppress(TypeError, ValueError):
                    settings_repo.set_app_setting("framework_collection_ttl_days", str(int(body["ttl_days"])))
            if "default_rag_top_k" in body:
                with contextlib.suppress(TypeError, ValueError):
                    settings_repo.set_app_setting("default_rag_top_k", str(int(body.get("default_rag_top_k", 4))))
            return jsonify({"status": "ok"})
        except Exception as e:
            error_log.error("webui_rag_routes.save_rag_collection_settings", exc_info=True)
            return _error_response(e)

    @bp.route("/rag/start", methods=["POST"])
    def rag_start() -> Any:
        try:
            ok, output, name = start_qdrant_service()
            status = 200 if ok else 500
            return jsonify({"ok": ok, "output": output, "container": name}), status
        except Exception as e:
            error_log.error("webui_rag_routes.rag_start", exc_info=True)
            return jsonify({"ok": False, "output": str(e), "container": os.getenv("QDRANT_CONTAINER_NAME", "qdrant")}), 500

    @bp.route("/rag/stop", methods=["POST"])
    def rag_stop() -> Any:
        try:
            ok, output, name = stop_qdrant_service()
            status = 200 if ok else 500
            return jsonify({"ok": ok, "output": output, "container": name}), status
        except Exception as e:
            error_log.error("webui_rag_routes.rag_stop", exc_info=True)
            return jsonify({"ok": False, "output": str(e), "container": os.getenv("QDRANT_CONTAINER_NAME", "qdrant")}), 500
