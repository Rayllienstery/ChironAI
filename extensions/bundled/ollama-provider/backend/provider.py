"""Full Ollama extension for the blind LLM runtime."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from llm_interactor.contracts import (
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ModelDescriptor,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderHealth,
    ProviderHostContext,
)


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
        for item in self._visible_model_entries():
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
                        "hidden": False,
                    },
                )
            )
        return out

    def invoke(self, request: LLMRequest) -> LLMResponse:
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
        return {
            "id": "ollama",
            "title": "Ollama",
            "icon": "network_node",
            "description": "Provider management, runtime diagnostics, and model operations.",
            "order": 50,
        }

    def get_tab_payload(self, *, runtime: Any | None = None) -> dict[str, Any]:
        health = self.health_check()
        all_models = self._all_model_entries()
        visible_models = self._visible_model_entries()
        hidden_ids = self._hidden_model_ids()
        selected_model = visible_models[0] if visible_models else (all_models[0] if all_models else None)
        selected_model_name = str((selected_model or {}).get("name") or (selected_model or {}).get("model") or "").strip()

        diagnostics = {
            "provider_id": self._provider_id,
            "extension_id": str(self._manifest.id),
            "base_url": self._base_url(),
            "chat_url": str(getattr(self._chat_client, "_url", "") or ""),
            "embed_url": self._embed_url(),
            "generate_url": self._generate_url(),
            "default_model": str(getattr(self._chat_client, "_model", "") or ""),
            "hidden_model_ids": sorted(hidden_ids),
            "visible_models": len(visible_models),
            "total_models": len(all_models),
            "health": {
                "ok": bool(health.ok),
                "status": health.status,
                "message": health.message,
                "details": dict(health.details or {}),
            },
        }

        schema = {
            "pages": [
                {
                    "id": "ollama-overview",
                    "title": "Ollama",
                    "sections": [
                        {
                            "id": "service",
                            "title": "Service",
                            "components": [
                                {
                                    "type": "status",
                                    "key": "provider_health",
                                    "label": "Health",
                                    "status": health.status,
                                    "message": health.message or ("Reachable" if health.ok else "Unavailable"),
                                },
                                {
                                    "type": "text",
                                    "key": "base_url",
                                    "label": "Base URL",
                                    "value": self._base_url() or "Not configured",
                                },
                                {
                                    "type": "text",
                                    "key": "default_model",
                                    "label": "Default model",
                                    "value": str(getattr(self._chat_client, "_model", "") or "Not configured"),
                                },
                                {
                                    "type": "action",
                                    "key": "refresh",
                                    "label": "Refresh",
                                    "action_id": "refresh",
                                    "variant": "secondary",
                                },
                                {
                                    "type": "action",
                                    "key": "start_service",
                                    "label": "Start Ollama",
                                    "action_id": "start_service",
                                    "variant": "primary",
                                    "disabled": bool(health.ok),
                                },
                                {
                                    "type": "action",
                                    "key": "stop_service",
                                    "label": "Stop Ollama",
                                    "action_id": "stop_service",
                                    "variant": "danger",
                                    "disabled": not bool(health.ok),
                                    "confirm": "Stop the Ollama service?",
                                },
                            ],
                        },
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
                                            "label": self._model_option_label(item),
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
                                    "rows": [
                                        {
                                            "id": str(item.get("name") or item.get("model") or ""),
                                            "size": item.get("size") or "",
                                            "modified_at": item.get("modified_at") or "",
                                            "hidden": "yes" if str(item.get("name") or item.get("model") or "") in hidden_ids else "",
                                        }
                                        for item in all_models
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
            return {"ok": True, "message": "Refreshed"}
        if action == "start_service":
            from api.http.service_control import start_ollama

            ok, output = start_ollama()
            return {"ok": bool(ok), "message": output}
        if action == "stop_service":
            from api.http.service_control import stop_ollama

            ok, output = stop_ollama(base_url=self._base_url(), default_port=11434)
            return {"ok": bool(ok), "message": output}

        model_name = str(
            payload.get("selected_model")
            or payload.get("model")
            or payload.get("pull_model_name")
            or ""
        ).strip()
        if action in {"show_model", "hide_model", "unhide_model", "delete_model"} and not model_name:
            raise ValueError("selected_model is required")

        if action == "show_model":
            from infrastructure.ollama.cli_runner import invoke_show

            details = invoke_show(base_url=self._base_url(), name=model_name, timeout=60.0)
            return {"ok": True, "message": f"Loaded details for {model_name}", "details": details}
        if action == "delete_model":
            from infrastructure.ollama.cli_runner import invoke_delete

            out = invoke_delete(base_url=self._base_url(), name=model_name, timeout=60.0)
            return {"ok": True, "message": f"Deleted {model_name}", "details": out}
        if action == "hide_model":
            from infrastructure.ollama.ollama_model_visibility import patch_hidden_ollama_model_ids

            updated = patch_hidden_ollama_model_ids(add=[model_name], remove=[])
            return {"ok": True, "message": f"Hidden {model_name}", "hidden_model_ids": updated}
        if action == "unhide_model":
            from infrastructure.ollama.ollama_model_visibility import patch_hidden_ollama_model_ids

            updated = patch_hidden_ollama_model_ids(add=[], remove=[model_name])
            return {"ok": True, "message": f"Unhid {model_name}", "hidden_model_ids": updated}
        if action == "pull_model":
            pull_name = str(payload.get("pull_model_name") or "").strip()
            if not pull_name:
                raise ValueError("pull_model_name is required")
            from infrastructure.ollama.cli_runner import iter_pull_objects

            last: dict[str, Any] = {}
            for item in iter_pull_objects(base_url=self._base_url(), name=pull_name, read_timeout=3600.0):
                if isinstance(item, dict):
                    last = item
            return {"ok": True, "message": f"Pull completed for {pull_name}", "details": last}
        raise ValueError(f"Unsupported action: {action}")

    def health_check(self) -> ProviderHealth:
        base_url = self._base_url()
        if not base_url:
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                status="missing_base_url",
                message="Could not derive Ollama base URL from chat client",
            )
        try:
            from infrastructure.ollama.cli_runner import invoke_ping

            data = invoke_ping(base_url=base_url, timeout=5.0)
            ok = bool(data.get("ok"))
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=ok,
                status="ok" if ok else "unreachable",
                message="" if ok else "Ollama is not reachable",
                details=dict(data or {}),
            )
        except Exception as e:
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                status="error",
                message=str(e),
            )

    def _invoke_embed(self, request: LLMRequest) -> LLMResponse:
        from infrastructure.ollama.embed_client import OllamaEmbeddingProvider

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
        from infrastructure.ollama.rerank_client import OllamaRerankClient

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

    def _all_model_entries(self) -> list[dict[str, Any]]:
        from infrastructure.ollama.cli_runner import invoke_tags

        base_url = self._base_url()
        if not base_url:
            return []
        try:
            data = invoke_tags(base_url=base_url, timeout=5.0)
        except Exception:
            return []
        models = data.get("models") if isinstance(data, dict) else []
        return [dict(item) for item in models if isinstance(item, dict)]

    def _visible_model_entries(self) -> list[dict[str, Any]]:
        from infrastructure.ollama.ollama_model_visibility import (
            filter_ollama_tag_entries_for_editors,
            get_hidden_ollama_model_ids,
        )

        raw = self._all_model_entries()
        return filter_ollama_tag_entries_for_editors(raw, get_hidden_ollama_model_ids())

    def _hidden_model_ids(self) -> set[str]:
        from infrastructure.ollama.ollama_model_visibility import get_hidden_ollama_model_ids

        return set(get_hidden_ollama_model_ids())

    def _model_option_label(self, item: dict[str, Any]) -> str:
        model_id = str(item.get("name") or item.get("model") or "").strip()
        if not model_id:
            return ""
        if model_id in self._hidden_model_ids():
            return f"{model_id} (hidden)"
        return model_id


def create_provider(host_context: ProviderHostContext, manifest: Any) -> OllamaProvider:
    return OllamaProvider(host_context, manifest)
