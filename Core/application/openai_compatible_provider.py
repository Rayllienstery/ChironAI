"""Host-level OpenAI-compatible upstream LLM provider."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import requests

from core.contracts.llm_runtime import (
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ModelDescriptor,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderHealth,
)

_MODELS_CACHE_TTL_SEC = 60.0


def _openai_chat_url(base_url: str) -> str:
    root = str(base_url or "").strip().rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def _openai_models_url(base_url: str) -> str:
    root = str(base_url or "").strip().rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/models"
    return f"{root}/v1/models"


def _headers_for_record(record: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    secret = str(record.get("api_key") or "").strip()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    org = str(record.get("organization") or "").strip()
    if org:
        headers["OpenAI-Organization"] = org
    for key, value in dict(record.get("default_headers") or {}).items():
        if key and value is not None:
            headers[str(key)] = str(value)
    return headers


def _ollama_body_to_openai(body: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": str(body.get("model") or ""),
        "messages": list(body.get("messages") or []),
        "stream": bool(body.get("stream", False)),
    }
    options = dict(body.get("options") or {})
    if "temperature" in options:
        payload["temperature"] = options["temperature"]
    if "top_p" in options:
        payload["top_p"] = options["top_p"]
    if body.get("max_tokens") is not None:
        payload["max_tokens"] = body.get("max_tokens")
    if isinstance(body.get("tools"), list):
        payload["tools"] = body["tools"]
    if body.get("tool_choice") not in (None, ""):
        payload["tool_choice"] = body.get("tool_choice")
    return payload


def _extract_assistant_text(raw: dict[str, Any]) -> str:
    message = raw.get("message")
    if isinstance(message, dict) and message.get("content") is not None:
        return str(message.get("content") or "")
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        msg = first.get("message") if isinstance(first.get("message"), dict) else {}
        if msg.get("content") is not None:
            return str(msg.get("content") or "")
        if first.get("text") is not None:
            return str(first.get("text") or "")
    return str(raw.get("response") or "")


class OpenAICompatibleProvider:
    """Builtin provider that forwards chat to an OpenAI-compatible HTTP API."""

    def __init__(self, record: dict[str, Any]) -> None:
        self._record = dict(record)
        self._provider_id = str(record.get("id") or "").strip()
        self._models_cache: tuple[float, list[ModelDescriptor]] | None = None

    def describe(self) -> ProviderDescriptor:
        title = str(self._record.get("display_name") or self._provider_id)
        return ProviderDescriptor(
            id=self._provider_id,
            extension_id="",
            title=title,
            description="Custom OpenAI-compatible upstream",
            capabilities=ProviderCapabilities(
                chat=True,
                streaming=True,
                tools=True,
                vision=True,
                model_listing=True,
                health_check=True,
            ),
            metadata={"source": "custom_openai", "base_url": str(self._record.get("base_url") or "")},
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: float = 120.0,
    ) -> requests.Response:
        return requests.request(
            method,
            url,
            headers=_headers_for_record(self._record),
            json=json_body,
            stream=stream,
            timeout=timeout,
        )

    def list_models(self) -> list[ModelDescriptor]:
        now = time.monotonic()
        if self._models_cache and now - self._models_cache[0] < _MODELS_CACHE_TTL_SEC:
            return list(self._models_cache[1])
        models: list[ModelDescriptor] = []
        try:
            response = self._request("GET", _openai_models_url(str(self._record.get("base_url") or "")), timeout=30.0)
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, list):
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    model_id = str(row.get("id") or "").strip()
                    if not model_id:
                        continue
                    models.append(
                        ModelDescriptor(
                            id=model_id,
                            provider_id=self._provider_id,
                            label=model_id,
                            description=str(row.get("owned_by") or ""),
                        )
                    )
        except Exception:
            models = []
        manual = [str(m).strip() for m in (self._record.get("manual_models") or []) if str(m).strip()]
        seen = {m.id for m in models}
        for model_id in manual:
            if model_id not in seen:
                models.append(
                    ModelDescriptor(
                        id=model_id,
                        provider_id=self._provider_id,
                        label=model_id,
                        description="manual",
                    )
                )
                seen.add(model_id)
        self._models_cache = (now, models)
        return list(models)

    def health_check(self) -> ProviderHealth:
        try:
            response = self._request("GET", _openai_models_url(str(self._record.get("base_url") or "")), timeout=15.0)
            ok = response.status_code < 400
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=ok,
                status="ok" if ok else "error",
                message="" if ok else f"HTTP {response.status_code}",
            )
        except Exception as exc:
            return ProviderHealth(
                provider_id=self._provider_id,
                ok=False,
                status="error",
                message=str(exc),
            )

    def invoke(self, request: LLMRequest) -> LLMResponse:
        if request.operation == "chat_api":
            body = _ollama_body_to_openai(dict(request.body or {}))
            response = self._request(
                "POST",
                _openai_chat_url(str(self._record.get("base_url") or "")),
                json_body=body,
                timeout=180.0,
            )
            response.raise_for_status()
            raw = response.json()
            if not isinstance(raw, dict):
                raw = {}
            text = _extract_assistant_text(raw)
            return LLMResponse(provider_id=self._provider_id, model=request.model, text=text, raw=raw)
        if request.operation == "chat":
            body = {
                "model": request.model,
                "messages": list(request.messages or []),
                "stream": False,
            }
            if request.options:
                body["options"] = dict(request.options)
            converted = _ollama_body_to_openai(body)
            response = self._request(
                "POST",
                _openai_chat_url(str(self._record.get("base_url") or "")),
                json_body=converted,
                timeout=180.0,
            )
            response.raise_for_status()
            raw = response.json()
            if not isinstance(raw, dict):
                raw = {}
            text = _extract_assistant_text(raw)
            return LLMResponse(provider_id=self._provider_id, model=request.model, text=text, raw=raw)
        raise RuntimeError(f"Unsupported invoke operation: {request.operation}")

    def stream_invoke(self, request: LLMRequest) -> Iterator[LLMStreamEvent]:
        if request.operation not in {"chat_api_stream_events", "chat"}:
            yield LLMStreamEvent(
                provider_id=self._provider_id,
                model=request.model,
                type="error",
                data=f"Unsupported stream operation: {request.operation}",
            )
            return
        body = dict(request.body or {})
        if request.operation == "chat":
            body = {
                "model": request.model,
                "messages": list(request.messages or []),
                "stream": True,
                "options": dict(request.options or {}),
            }
        payload = _ollama_body_to_openai({**body, "stream": True})
        try:
            response = self._request(
                "POST",
                _openai_chat_url(str(self._record.get("base_url") or "")),
                json_body=payload,
                stream=True,
                timeout=300.0,
            )
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                text = str(line).strip()
                if not text.startswith("data:"):
                    continue
                data_text = text[5:].strip()
                if data_text == "[DONE]":
                    yield LLMStreamEvent(
                        provider_id=self._provider_id,
                        model=request.model,
                        type="done",
                        data=None,
                    )
                    break
                try:
                    chunk = json.loads(data_text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                choices = chunk.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                first = choices[0] if isinstance(choices[0], dict) else {}
                delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
                content = delta.get("content")
                if content:
                    yield LLMStreamEvent(
                        provider_id=self._provider_id,
                        model=request.model,
                        type="content_delta",
                        data=str(content),
                    )
                if first.get("finish_reason"):
                    yield LLMStreamEvent(
                        provider_id=self._provider_id,
                        model=request.model,
                        type="done",
                        data=None,
                    )
                    break
        except Exception as exc:
            yield LLMStreamEvent(
                provider_id=self._provider_id,
                model=request.model,
                type="error",
                data=exc,
            )

    def register_http_routes(self, _blueprint: Any) -> None:
        return None

    def test_connection(self) -> dict[str, Any]:
        health = self.health_check()
        models = self.list_models() if health.ok else []
        return {
            "ok": health.ok,
            "status": health.status,
            "message": health.message,
            "model_count": len(models),
            "models": [{"id": m.id, "label": m.label} for m in models[:25]],
        }
