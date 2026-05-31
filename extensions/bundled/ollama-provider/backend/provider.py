"""Full Ollama extension for the blind LLM runtime."""

from __future__ import annotations

import os as _os
import sys as _sys

# Add this extension's backend directory to sys.path so sibling modules
# (model_brand, model_visibility, ollama_http, embed_client, rerank_client)
# can be imported as absolute names.  This is required because the extension
# loader uses importlib.util.spec_from_file_location which loads provider.py
# as a standalone module (no package context), so relative imports do not work.
_backend_dir = _os.path.dirname(_os.path.abspath(__file__))
if _backend_dir not in _sys.path:
    _sys.path.insert(0, _backend_dir)

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading
import time
from typing import Any
from urllib.parse import urlparse

from llm_interactor.contracts import (
    DockerContainerSpec,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ModelDescriptor,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderHealth,
    ProviderHostContext,
)

from model_brand import resolve_brand_key  # noqa: E402
from model_visibility import (  # noqa: E402
    filter_ollama_tag_entries_for_editors,
    get_hidden_ollama_model_ids,
    patch_hidden_ollama_model_ids,
)
from ollama_http import (  # noqa: E402
    invoke_delete,
    invoke_ping,
    invoke_raw_json,
    invoke_show,
    invoke_tags,
    iter_pull_objects,
    iter_raw_lines,
)
from embed_client import OllamaEmbeddingProvider  # noqa: E402
from rerank_client import OllamaRerankClient  # noqa: E402

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, dict[str, tuple[float, Any]]] = {}


def _cache_get(base_url: str, key: str, ttl_sec: float) -> Any | None:
    if not base_url or ttl_sec <= 0:
        return None
    now = time.monotonic()
    with _CACHE_LOCK:
        bucket = _CACHE.get(base_url)
        if not bucket:
            return None
        item = bucket.get(key)
        if not item:
            return None
        ts, value = item
        if (now - ts) <= ttl_sec:
            return value
        return None


def _cache_set(base_url: str, key: str, value: Any) -> None:
    if not base_url:
        return
    with _CACHE_LOCK:
        bucket = _CACHE.setdefault(base_url, {})
        bucket[key] = (time.monotonic(), value)


def _manifest_tab_ui(manifest: Any) -> dict[str, Any]:
    metadata = getattr(manifest, "metadata", {})
    if isinstance(metadata, dict) and isinstance(metadata.get("tab_ui"), dict):
        return dict(metadata["tab_ui"])
    raw = getattr(manifest, "tab_ui", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _tab_frame(manifest: Any) -> dict[str, Any]:
    tab_ui = _manifest_tab_ui(manifest)
    frame = tab_ui.get("frame")
    return dict(frame) if isinstance(frame, dict) else {}


def _tab_title(manifest: Any, fallback: str) -> str:
    tab_ui = _manifest_tab_ui(manifest)
    return str(tab_ui.get("title") or fallback).strip() or fallback


def _tab_icon(manifest: Any, fallback: str) -> str:
    tab_ui = _manifest_tab_ui(manifest)
    return str(tab_ui.get("icon") or getattr(manifest, "icon", "") or fallback).strip() or fallback


def _as_int(raw: str | None, default: int) -> int:
    try:
        return int(str(raw or "").strip())
    except Exception:
        return default


class OllamaProvider:
    """Trusted provider and extension surface for Ollama-backed capabilities."""

    def __init__(self, host_context: ProviderHostContext, manifest: Any) -> None:
        self._host = host_context
        self._manifest = manifest
        self._chat_client = host_context.chat_client
        self._provider_id = "ollama"
        self._capabilities = ProviderCapabilities(
            chat=True,
            embed=True,
            rerank=True,
            completions=False,
            streaming=True,
            tools=True,
            vision=True,
            model_listing=True,
            health_check=True,
            tab_ui=True,
            service_actions=True,
        )

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id=self._provider_id,
            extension_id=str(self._manifest.id),
            title=str(self._manifest.title),
            description=str(self._manifest.description),
            icon=str(self._manifest.icon),
            capabilities=self._capabilities,
            metadata={
                "chat_url": str(getattr(self._chat_client, "_url", "") or ""),
                "default_model": str(getattr(self._chat_client, "_model", "") or ""),
                "base_url": self._base_url(),
            },
        )

    def list_models(self) -> list[ModelDescriptor]:
        out: list[ModelDescriptor] = []
        # Listing models is used by UI/catalog endpoints; keep it responsive.
        for item in self._visible_model_entries(timeout_sec=2.0, cache_ttl_sec=30.0):
            model_id = str(item.get("name") or item.get("model") or "").strip()
            if not model_id:
                continue
            out.append(
                ModelDescriptor(
                    id=model_id,
                    provider_id=self._provider_id,
                    label=model_id,
                    description=f"Ollama model: {model_id}",
                    capabilities=self._capabilities,
                    metadata={
                        "size": item.get("size"),
                        "modified_at": item.get("modified_at"),
                        "family": item.get("_family"),
                        "brand_key": resolve_brand_key(model_id),
                        "hidden": False,
                    },
                )
            )
        return out

    def invoke(self, request: LLMRequest) -> LLMResponse:
        if request.operation == "raw_ollama":
            return self._invoke_raw_ollama(request)
        if request.operation == "embed":
            return self._invoke_embed(request)
        if request.operation == "rerank":
            return self._invoke_rerank(request)
        if self._chat_client is None:
            raise RuntimeError("chat_client is not available for Ollama provider")
        if request.operation == "chat":
            kwargs: dict[str, Any] = {
                "stream": bool(request.stream),
                "options": request.options,
            }
            if request.think is not None:
                kwargs["think"] = request.think
            text = self._chat_client.chat(request.messages, request.model, **kwargs)
            return LLMResponse(provider_id=self._provider_id, model=request.model, text=str(text or ""))
        if request.operation == "chat_api":
            payload = dict(request.body or {})
            raw = self._chat_client.chat_api(payload)
            message = raw.get("message") if isinstance(raw, dict) else {}
            text = ""
            if isinstance(message, dict):
                text = str(message.get("content") or "")
            return LLMResponse(
                provider_id=self._provider_id,
                model=request.model,
                text=text,
                raw=raw if isinstance(raw, dict) else {},
            )
        raise RuntimeError(f"Unsupported invoke operation: {request.operation}")

    def stream_invoke(self, request: LLMRequest) -> Iterator[LLMStreamEvent]:
        if request.operation == "raw_ollama":
            yield from self._stream_raw_ollama(request)
            return
        if self._chat_client is None:
            yield LLMStreamEvent(
                provider_id=self._provider_id,
                model=request.model,
                type="error",
                data="chat_client is not available for Ollama provider",
            )
            return
        if request.operation == "chat_api_stream_events":
            stream_fn = getattr(self._chat_client, "iter_chat_api_stream_events", None)
            if callable(stream_fn):
                for kind, data in stream_fn(dict(request.body or {})):
                    yield LLMStreamEvent(
                        provider_id=self._provider_id,
                        model=request.model,
                        type=str(kind),
                        data=data,
                    )
                return
            final_fn = getattr(self._chat_client, "chat_api_stream_final", None)
            if callable(final_fn):
                data = final_fn({**dict(request.body or {}), "stream": False})
                yield from self._yield_chat_api_events(request.model, data)
                return
            chat_api_fn = getattr(self._chat_client, "chat_api", None)
            if callable(chat_api_fn):
                data = chat_api_fn({**dict(request.body or {}), "stream": False})
                yield from self._yield_chat_api_events(request.model, data)
                return
        payload = dict(request.body or {})
        payload.setdefault("messages", list(request.messages))
        payload.setdefault("model", request.model)
        payload.setdefault("stream", True)
        stream_fn = getattr(self._chat_client, "iter_chat_api_stream_events", None)
        if callable(stream_fn):
            for kind, data in stream_fn(payload):
                yield LLMStreamEvent(
                    provider_id=self._provider_id,
                    model=request.model,
                    type=str(kind),
                    data=data,
                )
            return
        try:
            kwargs: dict[str, Any] = {
                "stream": False,
                "options": payload.get("options"),
            }
            if payload.get("think") is not None:
                kwargs["think"] = payload.get("think")
            text = self._chat_client.chat(
                payload.get("messages") or [],
                payload.get("model") or request.model,
                **kwargs,
            )
            if text:
                yield LLMStreamEvent(
                    provider_id=self._provider_id,
                    model=request.model,
                    type="content_delta",
                    data=str(text),
                )
            yield LLMStreamEvent(provider_id=self._provider_id, model=request.model, type="done", data={})
        except Exception as e:
            yield LLMStreamEvent(
                provider_id=self._provider_id,
                model=request.model,
                type="error",
                data=str(e),
            )

    def get_tab_descriptor(self, *, runtime: Any | None = None) -> dict[str, Any]:
        frame = _tab_frame(self._manifest)
        return {
            "id": "ollama",
            "title": _tab_title(self._manifest, "Ollama"),
            "icon": _tab_icon(self._manifest, "icons/ollama-light.svg"),
            "description": "Provider management, runtime diagnostics, and model operations.",
            "frame": frame,
            "order": 50,
        }

    def get_tab_payload(self, *, runtime: Any | None = None) -> dict[str, Any]:
        # UI should not block on slow/unreachable Ollama. Short timeouts + TTL cache; ping and
        # model list run concurrently (same worst-case as one slow hop, not sequential).
        base_url = self._base_url()
        hidden_ids = self._hidden_model_ids()
        hidden_frozen = frozenset(hidden_ids)

        # Hard bound for this endpoint: even if the underlying HTTP/CLI stalls, never block the UI.
        health_timeout_s = 1.0
        tags_timeout_s = 1.25
        docker_timeout_s = 1.0
        budget_s = 1.75

        t0 = time.monotonic()
        health: ProviderHealth
        all_models: list[dict[str, Any]]
        degraded_reason: str | None = None

        pool = ThreadPoolExecutor(max_workers=3)
        try:
            fut_health = pool.submit(lambda: self.health_check(timeout_sec=0.75, cache_ttl_sec=2.0))
            fut_models = pool.submit(
                lambda: self._all_model_entries(
                    timeout_sec=0.9,
                    cache_ttl_sec=30.0,
                    allow_stale=True,
                )
            )
            fut_docker = pool.submit(self._docker_state_snapshot)

            remaining = max(0.0, budget_s - (time.monotonic() - t0))
            try:
                health = fut_health.result(timeout=min(health_timeout_s, remaining) if remaining else 0.0)
            except TimeoutError:
                degraded_reason = degraded_reason or "health_timeout"
                health = ProviderHealth(
                    provider_id=self._provider_id,
                    ok=False,
                    status="timeout",
                    message="Timed out while checking Ollama health",
                    details={"timeout_s": health_timeout_s},
                )
            except Exception as e:
                degraded_reason = degraded_reason or "health_error"
                health = ProviderHealth(
                    provider_id=self._provider_id,
                    ok=False,
                    status="error",
                    message=str(e),
                )

            remaining = max(0.0, budget_s - (time.monotonic() - t0))
            try:
                all_models = fut_models.result(timeout=min(tags_timeout_s, remaining) if remaining else 0.0)
            except TimeoutError:
                degraded_reason = degraded_reason or "tags_timeout"
                stale = _cache_get(base_url, "tags", ttl_sec=365 * 24 * 3600.0) if base_url else None
                if isinstance(stale, list):
                    all_models = [dict(item) for item in stale if isinstance(item, dict)]
                else:
                    all_models = []
            except Exception:
                degraded_reason = degraded_reason or "tags_error"
                all_models = []

            remaining = max(0.0, budget_s - (time.monotonic() - t0))
            try:
                docker_state = fut_docker.result(timeout=min(docker_timeout_s, remaining) if remaining else 0.0)
            except TimeoutError:
                degraded_reason = degraded_reason or "docker_timeout"
                docker_state = {
                    "available": False,
                    "container_name": self._docker_container_name(),
                    "image": self._docker_image(),
                    "exists": None,
                    "running": None,
                    "status": "timeout",
                    "message": "Timed out while checking the Ollama Docker container.",
                    "action_hint": "refresh",
                }
            except Exception as e:
                degraded_reason = degraded_reason or "docker_error"
                docker_state = {
                    "available": False,
                    "container_name": self._docker_container_name(),
                    "image": self._docker_image(),
                    "exists": None,
                    "running": None,
                    "status": "error",
                    "message": str(e),
                    "action_hint": "refresh",
                }

            fut_health.cancel()
            fut_models.cancel()
            fut_docker.cancel()
        finally:
            # Do not let a stuck HTTP or Docker runtime probe hold the tab endpoint open.
            pool.shutdown(wait=False, cancel_futures=True)

        visible_models = filter_ollama_tag_entries_for_editors(all_models, hidden_frozen)
        selected_model = visible_models[0] if visible_models else (all_models[0] if all_models else None)
        selected_model_name = str((selected_model or {}).get("name") or (selected_model or {}).get("model") or "").strip()

        health_status = health.status
        health_message = health.message
        if not health.ok:
            docker_status = str(docker_state.get("status") or "")
            docker_message = str(docker_state.get("message") or "")
            if docker_status in {"container_missing", "container_stopped"} and docker_message:
                health_status = docker_status
                health_message = docker_message

        diagnostics = {
            "provider_id": self._provider_id,
            "extension_id": str(self._manifest.id),
            "base_url": base_url,
            "chat_url": str(getattr(self._chat_client, "_url", "") or ""),
            "embed_url": self._embed_url(),
            "generate_url": self._generate_url(),
            "default_model": str(getattr(self._chat_client, "_model", "") or ""),
            "hidden_model_ids": sorted(hidden_ids),
            "visible_models": len(visible_models),
            "total_models": len(all_models),
            "degraded_reason": degraded_reason,
            "docker": docker_state,
            "health": {
                "ok": bool(health.ok),
                "status": health_status,
                "message": health_message,
                "details": dict(health.details or {}),
            },
        }

        ctn = self._docker_container_name()
        schema = {
            "pages": [
                {
                    "id": "ollama-overview",
                    "title": "Ollama",
                    "sections": [
                        {
                            "id": "pull",
                            "title": "Pull model",
                            "components": [
                                {
                                    "type": "input",
                                    "key": "pull_model_name",
                                    "label": "Model name",
                                    "placeholder": "llama3.2:latest",
                                    "value": "",
                                },
                                {
                                    "type": "action",
                                    "key": "pull_model",
                                    "label": "Pull",
                                    "action_id": "pull_model",
                                    "variant": "primary",
                                    "payload_keys": ["pull_model_name"],
                                },
                            ],
                        },
                        {
                            "id": "models",
                            "title": "Model actions",
                            "components": [
                                {
                                    "type": "select",
                                    "key": "selected_model",
                                    "label": "Selected model",
                                    "value": selected_model_name,
                                    "options": [
                                        {
                                            "value": str(item.get("name") or item.get("model") or ""),
                                            "label": self._model_option_label(item, hidden_ids),
                                        }
                                        for item in all_models
                                    ],
                                },
                                {
                                    "type": "action",
                                    "key": "show_model",
                                    "label": "Show details",
                                    "action_id": "show_model",
                                    "variant": "secondary",
                                    "payload_keys": ["selected_model"],
                                },
                                {
                                    "type": "action",
                                    "key": "hide_model",
                                    "label": "Hide model",
                                    "action_id": "hide_model",
                                    "variant": "secondary",
                                    "payload_keys": ["selected_model"],
                                },
                                {
                                    "type": "action",
                                    "key": "unhide_model",
                                    "label": "Unhide model",
                                    "action_id": "unhide_model",
                                    "variant": "secondary",
                                    "payload_keys": ["selected_model"],
                                },
                                {
                                    "type": "action",
                                    "key": "delete_model",
                                    "label": "Delete model",
                                    "action_id": "delete_model",
                                    "variant": "danger",
                                    "payload_keys": ["selected_model"],
                                    "confirm": "Delete the selected Ollama model?",
                                },
                                {
                                    "type": "table",
                                    "key": "provider_models",
                                    "label": "Installed models",
                                    "columns": [
                                        {"key": "id", "label": "ID"},
                                        {"key": "size", "label": "Size"},
                                        {"key": "modified_at", "label": "Modified"},
                                        {"key": "hidden", "label": "Hidden"},
                                    ],
                                    "rows": self._build_model_rows(all_models, hidden_ids),
                                },
                            ],
                        },
                        {
                            "id": "cloud_models",
                            "title": "Cloud models (ollama.com)",
                            "components": [
                                {
                                    "type": "text",
                                    "key": "cloud_models_intro",
                                    "label": "About",
                                    "value": (
                                        "Models with the :cloud suffix run on Ollama Cloud. "
                                        "Authenticate once inside the same Ollama process Chiron uses (see steps). "
                                        "Docs: https://docs.ollama.com/cloud"
                                    ),
                                },
                                {
                                    "type": "steps",
                                    "key": "cloud_signin_steps",
                                    "label": "Sign in (Docker)",
                                    "steps": [
                                        {
                                            "id": "cloud_shell",
                                            "label": "Open a shell in the Ollama container",
                                            "command": f"docker exec -it {ctn} sh",
                                            "hint": (
                                                "Docker Desktop: Containers → your Ollama container → Exec / Terminal. "
                                                "If the name differs, set OLLAMA_CONTAINER_NAME or edit the command."
                                            ),
                                        },
                                        {
                                            "id": "cloud_signin_cmd",
                                            "label": "Run sign-in and complete the browser/device flow",
                                            "command": "ollama signin",
                                            "hint": "When finished, return here and try your cloud model again.",
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "id": "diagnostics",
                            "title": "Diagnostics",
                            "components": [
                                {
                                    "type": "diagnostics",
                                    "key": "provider_diagnostics",
                                    "label": "Runtime details",
                                    "value": diagnostics,
                                },
                            ],
                        },
                    ],
                }
            ]
        }
        return {
            "title": _tab_title(self._manifest, "Ollama"),
            "icon": _tab_icon(self._manifest, "icons/ollama-light.svg"),
            "frame": _tab_frame(self._manifest),
            "schema": schema,
            "state": {
                "provider_id": self._provider_id,
                "extension_id": str(self._manifest.id),
            },
        }

    def run_action(
        self,
        action_id: str,
        payload: dict[str, Any],
        *,
        runtime: Any | None = None,
    ) -> dict[str, Any]:
        action = str(action_id or "").strip()
        if action == "refresh":
            return {"ok": True, "message": "Refreshed", "details": {}}
        if action == "start_service":
            return self._start_service_with_docker()
        if action == "stop_service":
            return self._stop_service_with_docker()

        model_name = str(
            payload.get("selected_model")
            or payload.get("model")
            or payload.get("pull_model_name")
            or ""
        ).strip()
        if action in {"show_model", "hide_model", "unhide_model", "delete_model"} and not model_name:
            try:
                hidden_ids = set(self._hidden_model_ids() or [])
                visible_models = list(self._visible_model_entries(timeout_sec=2.0, cache_ttl_sec=0.0))
                all_models = list(self._all_model_entries(timeout_sec=2.0, cache_ttl_sec=0.0))
                fallback = (visible_models[0] if visible_models else (all_models[0] if all_models else None)) or {}
                fallback_name = str(fallback.get("name") or fallback.get("model") or "").strip()
                if fallback_name and fallback_name not in hidden_ids:
                    model_name = fallback_name
            except Exception:
                # Preserve original error below; action validation should not crash on fallback lookup.
                pass
            if not model_name:
                raise ValueError("selected_model is required (no default model could be inferred)")

        if action == "show_model":
            details = invoke_show(base_url=self._base_url(), name=model_name, timeout=60.0)
            return {"ok": True, "message": f"Loaded details for {model_name}", "details": details}
        if action == "delete_model":
            invoke_delete(base_url=self._base_url(), name=model_name, timeout=60.0)
            # Omit details: delete API payloads are not model records; the WebUI treats details as Model Details data.
            return {"ok": True, "message": f"Deleted {model_name}", "details": {}}
        if action == "hide_model":
            updated = patch_hidden_ollama_model_ids(
                self._host.get_settings_repository(), add=[model_name], remove=[]
            )
            return {
                "ok": True,
                "message": f"Hidden {model_name}",
                "details": {"model": model_name},
                "hidden_model_ids": updated,
            }
        if action == "unhide_model":
            updated = patch_hidden_ollama_model_ids(
                self._host.get_settings_repository(), add=[], remove=[model_name]
            )
            return {
                "ok": True,
                "message": f"Unhid {model_name}",
                "details": {"model": model_name},
                "hidden_model_ids": updated,
            }
        if action == "pull_model":
            pull_name = str(payload.get("pull_model_name") or "").strip()
            if not pull_name:
                raise ValueError("pull_model_name is required")
            last: dict[str, Any] = {}
            for item in iter_pull_objects(base_url=self._base_url(), name=pull_name, read_timeout=3600.0):
                if isinstance(item, dict):
                    last = item
            return {"ok": True, "message": f"Pull completed for {pull_name}", "details": last}
        raise ValueError(f"Unsupported action: {action}")

    def health_check(self, *, timeout_sec: float = 5.0, cache_ttl_sec: float = 0.0) -> ProviderHealth:
        base_url = self._base_url()
        if not base_url:
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                status="missing_base_url",
                message="Could not derive Ollama base URL from chat client",
            )
        if cache_ttl_sec > 0:
            cached = _cache_get(base_url, "health", cache_ttl_sec)
            if isinstance(cached, ProviderHealth):
                return cached
        try:
            data = invoke_ping(base_url=base_url, timeout=float(timeout_sec))
            ok = bool(data.get("ok"))
            health = ProviderHealth(
                provider_id=self._provider_id,
                ok=ok,
                status="ok" if ok else "unreachable",
                message="" if ok else "Ollama is not reachable",
                details=dict(data or {}),
            )
            if cache_ttl_sec > 0:
                _cache_set(base_url, "health", health)
            return health
        except Exception as e:
            health = ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                status="error",
                message=str(e),
            )
            if cache_ttl_sec > 0:
                _cache_set(base_url, "health", health)
            return health

    def _invoke_embed(self, request: LLMRequest) -> LLMResponse:
        provider = OllamaEmbeddingProvider(base_url=self._embed_url(), model=request.model)
        texts = [x for x in (request.input_texts or []) if isinstance(x, str)]
        if texts:
            embeddings = provider.embed_batch(texts)
            return LLMResponse(
                provider_id=self._provider_id,
                model=request.model,
                raw={"embeddings": embeddings},
            )
        text = str(request.input_text or "")
        embedding = provider.embed(text)
        return LLMResponse(
            provider_id=self._provider_id,
            model=request.model,
            raw={"embedding": embedding, "embeddings": [embedding]},
        )

    def _invoke_rerank(self, request: LLMRequest) -> LLMResponse:
        client = OllamaRerankClient(base_url=self._generate_url(), model=request.model)
        response_text = client.rerank(
            str(request.rerank_query or ""),
            str(request.rerank_prompt or ""),
        )
        return LLMResponse(
            provider_id=self._provider_id,
            model=request.model,
            text=str(response_text or ""),
            raw={"response": response_text},
        )

    def _invoke_raw_ollama(self, request: LLMRequest) -> LLMResponse:
        metadata = dict(request.metadata or {})
        segment = str(metadata.get("api_segment") or "").strip()
        if not segment:
            raise RuntimeError("raw_ollama api_segment is required")
        data = invoke_raw_json(
            base_url=self._base_url(),
            api_segment=segment,
            method=str(metadata.get("method") or "POST"),
            body=dict(request.body or {}),
            params=metadata.get("params") if isinstance(metadata.get("params"), dict) else None,
            headers=metadata.get("headers") if isinstance(metadata.get("headers"), dict) else None,
            timeout=float(metadata.get("timeout") or 600.0),
        )
        return LLMResponse(provider_id=self._provider_id, model=request.model, raw=data if isinstance(data, dict) else {})

    def _stream_raw_ollama(self, request: LLMRequest) -> Iterator[LLMStreamEvent]:
        metadata = dict(request.metadata or {})
        segment = str(metadata.get("api_segment") or "").strip()
        if not segment:
            yield LLMStreamEvent(
                provider_id=self._provider_id,
                model=request.model,
                type="error",
                data="raw_ollama api_segment is required",
            )
            return
        try:
            for line in iter_raw_lines(
                base_url=self._base_url(),
                api_segment=segment,
                body=dict(request.body or {}),
                headers=metadata.get("headers") if isinstance(metadata.get("headers"), dict) else None,
                read_timeout=float(metadata.get("read_timeout") or 86400.0),
            ):
                yield LLMStreamEvent(provider_id=self._provider_id, model=request.model, type="raw_line", data=line)
        except Exception as e:
            yield LLMStreamEvent(provider_id=self._provider_id, model=request.model, type="error", data=str(e))

    def _docker_runtime(self) -> Any | None:
        runtime = getattr(self._host, "docker_runtime", None)
        if runtime is not None:
            return runtime
        metadata = getattr(self._host, "metadata", {}) or {}
        if isinstance(metadata, dict):
            return metadata.get("docker_runtime")
        return None

    def _docker_unavailable(self) -> dict[str, Any]:
        return {
            "ok": False,
            "message": "Docker runtime is unavailable",
            "error": "Docker runtime is unavailable",
            "details": {},
        }

    def _docker_state_snapshot(self) -> dict[str, Any]:
        container_name = self._docker_container_name()
        image = self._docker_image()
        docker = self._docker_runtime()
        if docker is None:
            return {
                "available": False,
                "container_name": container_name,
                "image": image,
                "exists": None,
                "running": None,
                "status": "docker_unavailable",
                "message": "Docker runtime is unavailable.",
                "action_hint": "refresh",
            }

        try:
            state = None
            inspect = getattr(docker, "inspect_container", None)
            if callable(inspect):
                state = inspect(container_name)
                exists = bool(getattr(state, "exists", False))
                running = bool(getattr(state, "running", False)) if exists else False
            else:
                exists_fn = getattr(docker, "container_exists", None)
                running_fn = getattr(docker, "container_running", None)
                exists = bool(exists_fn(container_name)) if callable(exists_fn) else None
                running = bool(running_fn(container_name)) if callable(running_fn) and exists else False
        except Exception as e:
            return {
                "available": True,
                "container_name": container_name,
                "image": image,
                "exists": None,
                "running": None,
                "status": "error",
                "message": f"Could not inspect Ollama container {container_name}: {e}",
                "action_hint": "refresh",
            }

        if exists is None:
            return {
                "available": True,
                "container_name": container_name,
                "image": image,
                "exists": None,
                "running": None,
                "status": "unknown",
                "message": f"Docker runtime cannot inspect Ollama container {container_name}.",
                "action_hint": "refresh",
            }
        if not exists:
            return {
                "available": True,
                "container_name": container_name,
                "image": image,
                "exists": False,
                "running": False,
                "status": "container_missing",
                "message": f"Ollama container {container_name} does not exist. Download and create it from {image}.",
                "action_hint": "download",
            }
        if not running:
            return {
                "available": True,
                "container_name": container_name,
                "image": image,
                "exists": True,
                "running": False,
                "status": "container_stopped",
                "message": f"Ollama container {container_name} exists but is stopped.",
                "action_hint": "start",
            }
        return {
            "available": True,
            "container_name": container_name,
            "image": image,
            "exists": True,
            "running": True,
            "status": "container_running",
            "message": f"Ollama container {container_name} is running.",
            "action_hint": "stop",
        }

    def _docker_container_name(self) -> str:
        import os

        return (os.getenv("OLLAMA_CONTAINER_NAME") or "chironai-ollama").strip() or "chironai-ollama"

    def _docker_image(self) -> str:
        import os

        return (os.getenv("OLLAMA_DOCKER_IMAGE") or "ollama/ollama:latest").strip() or "ollama/ollama:latest"

    def _docker_base_url(self) -> str:
        import os

        raw_base = (self._base_url() or os.getenv("OLLAMA_BASE_URL") or "").strip().rstrip("/")
        if raw_base:
            return raw_base if "://" in raw_base else f"http://{raw_base}"
        port = _as_int(os.getenv("OLLAMA_PORT"), 11434)
        return f"http://localhost:{port}"

    def _docker_host_port(self) -> int:
        import os

        base = self._docker_base_url()
        parsed = urlparse(base if "://" in base else f"http://{base}")
        return int(parsed.port or _as_int(os.getenv("OLLAMA_PORT"), 11434))

    def _docker_volume(self) -> str:
        import os

        return (os.getenv("OLLAMA_DOCKER_VOLUME") or "ollama_models:/root/.ollama").strip()

    def _docker_spec(self) -> Any:
        import os

        host_port = self._docker_host_port()
        volume = self._docker_volume()
        volumes = [volume] if volume else []
        env: dict[str, str] = {"OLLAMA_HOST": "0.0.0.0:11434"}
        return DockerContainerSpec(
            name=self._docker_container_name(),
            image=self._docker_image(),
            ports=[f"{host_port}:11434"],
            env=env,
            volumes=volumes,
            restart=(os.getenv("OLLAMA_DOCKER_RESTART") or "unless-stopped").strip(),
            labels={
                "chironai.extension": str(self._manifest.id),
                "chironai.provider": self._provider_id,
            },
        )

    def _start_service_with_docker(self) -> dict[str, Any]:
        docker = self._docker_runtime()
        if docker is None:
            return self._docker_unavailable()
        try:
            spec = self._docker_spec()
            ensured = docker.ensure_container(spec)
            if not bool(ensured.get("ok")):
                return {"ok": False, "message": ensured.get("details") or ensured.get("error") or "Failed to start Ollama", "details": ensured}
            health = docker.wait_http(self._docker_base_url(), path="/api/tags", timeout=60.0, interval=1.0)
            if not bool(health.get("ok")):
                return {
                    "ok": False,
                    "message": f"Ollama container started but health check failed: {health.get('error') or 'timeout'}",
                    "details": {"container": ensured, "health": health},
                }
            return {
                "ok": True,
                "message": f"Ollama container {spec.name} is running",
                "details": {"container": ensured, "health": health, "base_url": self._docker_base_url()},
            }
        except Exception as e:
            return {"ok": False, "message": str(e), "error": str(e), "details": {}}

    def _stop_service_with_docker(self) -> dict[str, Any]:
        docker = self._docker_runtime()
        if docker is None:
            return self._docker_unavailable()
        try:
            result = docker.stop_container(self._docker_container_name())
            return {
                "ok": bool(result.get("ok")),
                "message": result.get("message") or result.get("details") or result.get("error") or "",
                "details": result,
            }
        except Exception as e:
            return {"ok": False, "message": str(e), "error": str(e), "details": {}}

    def _yield_chat_api_events(self, model: str, data: Any) -> Iterator[LLMStreamEvent]:
        payload = data if isinstance(data, dict) else {}
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        if content:
            yield LLMStreamEvent(
                provider_id=self._provider_id,
                model=model,
                type="content_delta",
                data=str(content),
            )
        tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
        if isinstance(tool_calls, list) and tool_calls:
            yield LLMStreamEvent(
                provider_id=self._provider_id,
                model=model,
                type="tool_calls",
                data=tool_calls,
            )
        yield LLMStreamEvent(
            provider_id=self._provider_id,
            model=model,
            type="done",
            data=payload,
        )

    def _base_url(self) -> str:
        raw = str(getattr(self._chat_client, "_url", "") or "").rstrip("/")
        if raw.endswith("/api/chat"):
            return raw[: -len("/api/chat")]
        return raw

    def _embed_url(self) -> str:
        base = self._base_url().rstrip("/")
        return f"{base}/api/embed" if base else ""

    def _generate_url(self) -> str:
        base = self._base_url().rstrip("/")
        return f"{base}/api/generate" if base else ""

    def _all_model_entries(
        self,
        *,
        timeout_sec: float = 5.0,
        cache_ttl_sec: float = 0.0,
        allow_stale: bool = False,
    ) -> list[dict[str, Any]]:
        base_url = self._base_url()
        if not base_url:
            return []
        if cache_ttl_sec > 0:
            cached = _cache_get(base_url, "tags", cache_ttl_sec)
            if isinstance(cached, list):
                return [dict(item) for item in cached if isinstance(item, dict)]
        try:
            data = invoke_tags(base_url=base_url, timeout=float(timeout_sec))
        except Exception:
            if allow_stale:
                stale = _cache_get(base_url, "tags", ttl_sec=365 * 24 * 3600.0)
                if isinstance(stale, list):
                    return [dict(item) for item in stale if isinstance(item, dict)]
            return []
        models = data.get("models") if isinstance(data, dict) else []
        out = [dict(item) for item in models if isinstance(item, dict)]
        if cache_ttl_sec > 0:
            _cache_set(base_url, "tags", out)
        return out

    def _visible_model_entries(self, *, timeout_sec: float = 5.0, cache_ttl_sec: float = 0.0) -> list[dict[str, Any]]:
        raw = self._all_model_entries(timeout_sec=timeout_sec, cache_ttl_sec=cache_ttl_sec, allow_stale=True)
        repo = self._host.get_settings_repository()
        return filter_ollama_tag_entries_for_editors(raw, get_hidden_ollama_model_ids(repo))

    def _hidden_model_ids(self) -> set[str]:
        return set(get_hidden_ollama_model_ids(self._host.get_settings_repository()))

    def _model_option_label(self, item: dict[str, Any], hidden_ids: set[str]) -> str:
        model_id = str(item.get("name") or item.get("model") or "").strip()
        if not model_id:
            return ""
        if model_id in hidden_ids:
            return f"{model_id} (hidden)"
        return model_id

    def _build_model_rows(
        self,
        all_models: list[dict[str, Any]],
        hidden_ids: set[str],
    ) -> list[dict[str, Any]]:
        base_url = self._base_url()
        rows: list[dict[str, Any]] = []
        show_futs: list[tuple[str, Any]] = []

        with ThreadPoolExecutor(max_workers=8) as pool:
            for item in all_models:
                model_id = str(item.get("name") or item.get("model") or "").strip()
                row = {
                    "id": model_id,
                    "size": item.get("size") or "",
                    "modified_at": item.get("modified_at") or "",
                    "hidden": "yes" if model_id in hidden_ids else "",
                }
                if model_id:
                    fut = pool.submit(
                        invoke_show,
                        base_url=base_url,
                        name=model_id,
                        timeout=2.0,
                    )
                    show_futs.append((model_id, fut))
                rows.append(row)

            for model_id, fut in show_futs:
                try:
                    details = fut.result(timeout=3.0)
                    if isinstance(details, dict):
                        row = next((r for r in rows if r["id"] == model_id), None)
                        if row is not None:
                            mi = details.get("model_info") or {}
                            if isinstance(mi, dict):
                                row["model_info"] = dict(mi)
                            caps = details.get("capabilities")
                            if isinstance(caps, list):
                                row["capabilities"] = list(caps)
                except Exception:
                    pass

        return rows


def create_provider(host_context: ProviderHostContext, manifest: Any) -> OllamaProvider:
    return OllamaProvider(host_context, manifest)



# ---------------------------------------------------------------------------
# Module-level blueprint hook — called by the project at startup via
# filesystem discovery (_register_extension_http_routes in webui_routes.py).
# Uses current_app at request time; no import from infrastructure.* here.
# ---------------------------------------------------------------------------

_EXTENSION_ID = "ollama-provider"
_PROVIDER_ID = "ollama"


def register_http_routes_on_blueprint(blueprint: Any) -> None:  # noqa: C901 (complexity ok for route block)
    """Register all Ollama HTTP routes on the host blueprint.

    Called once at startup by ``webui_routes._register_extension_http_routes``.
    Route handlers close over ``current_app`` so they resolve the running
    extension service at request time.
    """
    import json as _json
    import logging as _logging

    from flask import Response, current_app, jsonify, request, stream_with_context

    try:
        from error_manager.http import error_response as _error_response
    except Exception:
        def _error_response(err: Any, status: int = 500) -> Any:  # type: ignore[misc]
            return jsonify({"error": str(err)}), status

    _log = _logging.getLogger("webui.ollama_provider")

    # ---- dispatch helpers -------------------------------------------------

    def _svc() -> Any:
        return current_app.extensions.get("llm_extensions_service")

    def _runtime() -> Any:
        svc = _svc()
        return current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)

    def _default_provider_row() -> dict[str, Any] | None:
        svc = _svc()
        if svc is None:
            return None
        try:
            rows = svc.provider_rows(_runtime())
        except Exception:
            return None
        for row in rows:
            if str(row.get("provider_id") or "").strip() == _PROVIDER_ID:
                return row
        return rows[0] if rows else None

    def _run_action(action_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        svc = _svc()
        rt = _runtime()
        if svc is None or rt is None:
            raise RuntimeError("LLM extension service is unavailable")
        return svc.run_extension_action(_EXTENSION_ID, action_id, payload=dict(payload or {}), runtime=rt)

    def _tab_payload() -> dict[str, Any]:
        svc = _svc()
        rt = _runtime()
        if svc is None or rt is None:
            raise RuntimeError("LLM extension service is unavailable")
        return svc.extension_tab_payload(_EXTENSION_ID, runtime=rt)

    def _shutdown_server() -> None:
        func = request.environ.get("werkzeug.server.shutdown")
        if func is not None:
            func()
            return
        import os as _os
        _os.exit(0)

    # ---- routes -----------------------------------------------------------

    @blueprint.route("/ollama/status", methods=["GET"])
    def ollama_status() -> Any:
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

    @blueprint.route("/ollama/start", methods=["POST"])
    def ollama_start() -> Any:
        try:
            result = _run_action("start_service")
            status = 200 if bool(result.get("ok")) else 500
            return jsonify({"ok": bool(result.get("ok")), "output": result.get("message") or ""}), status
        except Exception as e:
            _log.error("ollama_start: %s", e, exc_info=True)
            return jsonify({"ok": False, "output": str(e)}), 500

    @blueprint.route("/ollama/stop", methods=["POST"])
    def ollama_stop() -> Any:
        try:
            result = _run_action("stop_service")
            status = 200 if bool(result.get("ok")) else 500
            return jsonify({"ok": bool(result.get("ok")), "output": result.get("message") or ""}), status
        except Exception as e:
            _log.error("ollama_stop: %s", e, exc_info=True)
            return jsonify({"ok": False, "output": str(e)}), 500

    @blueprint.route("/ollama/library", methods=["GET"])
    def ollama_library() -> Any:
        try:
            payload = _tab_payload()
            schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else {}
            rows: list[dict[str, Any]] = []
            hidden_ids: list[str] = []
            diagnostics: dict[str, Any] = {}
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
            _log.warning("ollama_library: %s", e)
            return jsonify({"ok": False, "url": None, "models": [], "hidden_ids": [], "error": str(e)})

    @blueprint.route("/ollama/hidden", methods=["PATCH"])
    def ollama_hidden_patch() -> Any:
        body = request.get_json(silent=True) or {}
        add = body.get("add") if isinstance(body.get("add"), list) else []
        remove = body.get("remove") if isinstance(body.get("remove"), list) else []
        try:
            updated: list[str] = []
            for model_name in add:
                result = _run_action("hide_model", {"selected_model": str(model_name)})
                if isinstance(result.get("hidden_model_ids"), list):
                    updated = [str(x) for x in result.get("hidden_model_ids") if str(x).strip()]
            for model_name in remove:
                result = _run_action("unhide_model", {"selected_model": str(model_name)})
                if isinstance(result.get("hidden_model_ids"), list):
                    updated = [str(x) for x in result.get("hidden_model_ids") if str(x).strip()]
            return jsonify({"ok": True, "hidden_ids": updated})
        except Exception as e:
            _log.error("ollama_hidden_patch: %s", e, exc_info=True)
            return jsonify({"ok": False, "error": str(e)}), 500

    @blueprint.route("/ollama/show", methods=["POST"])
    def ollama_show_model() -> Any:
        body = request.get_json(silent=True) or {}
        model = (body.get("model") or "").strip()
        if not model:
            return jsonify({"ok": False, "error": "model is required"}), 400
        try:
            result = _run_action("show_model", {"selected_model": model})
            return jsonify({"ok": bool(result.get("ok", True)), "details": result.get("details") or {}})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 502

    @blueprint.route("/ollama/delete", methods=["POST"])
    def ollama_delete_model() -> Any:
        body = request.get_json(silent=True) or {}
        model = (body.get("model") or "").strip()
        if not model:
            return jsonify({"ok": False, "error": "model is required"}), 400
        try:
            result = _run_action("delete_model", {"selected_model": model})
            return jsonify({"ok": bool(result.get("ok", True)), "result": result.get("details") or result.get("result") or {}})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 502

    @blueprint.route("/ollama/pull", methods=["POST"])
    def ollama_pull_stream() -> Any:
        body = request.get_json(silent=True) or {}
        model = (body.get("model") or "").strip()
        if not model:
            return _error_response("model is required", 400)
        row = _default_provider_row() or {}
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        base_url = str(metadata.get("base_url") or metadata.get("chat_url") or "").strip()
        if base_url.endswith("/api/chat"):
            base_url = base_url[: -len("/api/chat")]
        base_url = base_url.rstrip("/")
        if not base_url:
            try:
                payload = _tab_payload()
                schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else {}
                for page in schema.get("pages") or []:
                    for section in (page.get("sections") if isinstance(page, dict) else []) or []:
                        for component in (section.get("components") if isinstance(section, dict) else []) or []:
                            if isinstance(component, dict) and component.get("type") == "diagnostics":
                                value = component.get("value") if isinstance(component.get("value"), dict) else {}
                                base_url = str(value.get("base_url") or "").strip().rstrip("/")
                                break
            except Exception:
                base_url = ""
        if not base_url:
            return _error_response("Could not resolve Ollama base URL", 503)

        def generate():
            try:
                for item in iter_pull_objects(base_url=base_url, name=model, read_timeout=3600.0):
                    if isinstance(item, dict):
                        yield _json.dumps(item, ensure_ascii=False) + "\n"
                yield _json.dumps({"ok": True, "status": "success", "model": model}, ensure_ascii=False) + "\n"
            except Exception as e:
                _log.error("ollama_pull_stream: %s", e, exc_info=True)
                yield _json.dumps({"ok": False, "error": str(e), "status": "error"}, ensure_ascii=False) + "\n"

        return Response(
            stream_with_context(generate()),
            mimetype="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @blueprint.route("/server/stop", methods=["POST"])
    def server_stop() -> Any:
        try:
            _log.info("Received WebUI shutdown request")
            _shutdown_server()
            return jsonify({"status": "stopping"})
        except Exception as e:
            _log.error("server_stop: %s", e, exc_info=True)
            return _error_response(e)
