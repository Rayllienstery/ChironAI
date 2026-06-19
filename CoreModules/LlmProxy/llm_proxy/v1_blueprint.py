"""Flask blueprint for OpenAI-compatible /v1 routes."""

from __future__ import annotations

import contextlib
import logging
import os
from typing import TYPE_CHECKING, Any

from flask import Blueprint, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from core.bootstrap.import_paths import ensure_import_path

_LLM_PROXY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # CoreModules/LlmProxy
_CORE_MODULES_DIR = os.path.dirname(_LLM_PROXY_DIR)  # CoreModules/
_ERROR_MANAGER_DIR = os.path.join(_CORE_MODULES_DIR, "ErrorManager")
ensure_import_path("error_manager", _ERROR_MANAGER_DIR)

from error_manager.http import error_response as _error_response

from config import get_v1_include_autocomplete_logical_model
from llm_proxy.anthropic_compat import (
    anthropic_messages_request_to_openai_body,
    anthropic_models_list_payload,
    iter_anthropic_sse_from_openai_sse_lines,
    openai_chat_completion_to_anthropic_message,
    wants_anthropic_models_list,
)
from llm_proxy.api_key import verify_proxy_api_key
from llm_proxy.apply_edit import run_apply_file_edit
from llm_proxy.chat_completions import run_chat_completions
from llm_proxy.external_ingest import run_external_docs_ingest
from llm_proxy.v1_models import (
    _openai_build_model_rows,
    _openai_client_capability_model_row,
    _openai_model_rows,
)
from llm_proxy.v1_responses import (
    _RESPONSES_CHAIN_IDS,
    _RESPONSES_HISTORY,
    _RESPONSES_HISTORY_MAX,
    _chat_completion_to_responses_json,
    _chat_message_to_responses_output_items,
    _responses_chain_id_for_request,
    _responses_chain_id_put,
    _responses_history_put,
    _responses_input_to_openai_messages,
    _responses_normalize_tools,
    _responses_request_to_openai_chat_body,
    _responses_sse_payload,
)
from llm_proxy.workspace import set_workspace_root

if TYPE_CHECKING:
    from llm_proxy.contracts import LlmProxyWiring

_V1_LOG = logging.getLogger("llm_proxy")


def _request_proxy_api_key() -> str:
    auth = str(request.headers.get("Authorization") or "").strip()
    prefix = "Bearer "
    if auth.startswith(prefix):
        return auth[len(prefix) :].strip()
    return str(request.headers.get("x-api-key") or "").strip()


def _openai_error_response(message: str, error_type: str, status: int):
    return jsonify({"error": {"type": error_type, "message": message}}), status


def _post_body_is_openai_completions_shape(body: object) -> bool:
    """
    True when the client sent a legacy completions request (``prompt``/``input``)
    without a non-empty ``messages`` list â€” e.g. Zed edit prediction with API URL ending in ``/v1``.
    """
    if not isinstance(body, dict):
        return False
    messages = body.get("messages")
    if isinstance(messages, list) and len(messages) > 0:
        return False
    if body.get("prompt") is not None:
        return True
    return bool(body.get("input"))


def _inbound_request_id_from_headers() -> str:
    return str(request.headers.get("x-trace-id") or request.headers.get("x-request-id") or "").strip()


def _with_proxy_trace_meta(body: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(body)
    existing = out.get("_proxy_trace_meta")
    meta = dict(existing) if isinstance(existing, dict) else {}
    for key, value in extra.items():
        if value is None:
            continue
        if isinstance(value, str):
            v = value.strip()
            if not v:
                continue
            meta[key] = v
            continue
        meta[key] = value
    if meta:
        out["_proxy_trace_meta"] = meta
    return out


def create_v1_blueprint(wiring: LlmProxyWiring) -> Blueprint:
    """Register /v1/* routes; call `set_workspace_root` from `wiring.runtime`."""
    set_workspace_root(wiring.workspace_root)

    bp = Blueprint("llm_proxy_v1", __name__)

    @bp.errorhandler(Exception)
    def _handle_unexpected_exception(error: Exception):
        if isinstance(error, HTTPException):
            return error
        with contextlib.suppress(Exception):
            wiring.log_webui_error(
                "rag_routes.v1_unhandled",
                error,
                {
                    "stage": "unhandled_exception",
                    "path": request.path,
                    "method": request.method,
                    "endpoint": request.endpoint or "",
                },
            )
        return _error_response(error, status=500)

    @bp.before_request
    def _require_proxy_api_key():
        path = request.path or ""
        if path != "/v1" and not path.startswith("/v1/"):
            return None
        supplied = _request_proxy_api_key()
        configured, valid = verify_proxy_api_key(wiring.get_settings_repository(), supplied)
        if not configured:
            return _openai_error_response(
                "Chiron proxy API key is not configured",
                "server_configuration_error",
                503,
            )
        if not supplied or not valid:
            return _openai_error_response(
                "Invalid or missing API key",
                "authentication_error",
                401,
            )
        return None

    @bp.route("/v1", methods=["GET", "POST"])
    def v1_root():
        # Chat-shaped POSTs are accepted here for clients configured with a /v1 base URL.
        if request.method == "POST":
            _raw = request.get_json(force=True, silent=True) or {}
            if _post_body_is_openai_completions_shape(_raw):
                return _openai_error_response(
                    "Legacy OpenAI completions are no longer supported by the core proxy; use /v1/chat/completions or an extension-owned provider endpoint.",
                    "unsupported_endpoint",
                    404,
                )
            return run_chat_completions(wiring)
        return jsonify({"object": "api", "version": "v1"})

    @bp.route("/v1/models", methods=["GET"])
    def list_models():
        # Note: build rows are OpenAI-shaped model objects, with extra client capability
        # fields such as `supports_vision`, `attachment`, `modalities`, and `metadata`.
        if wants_anthropic_models_list(request.headers):
            ids: list[str] = []
            if get_v1_include_autocomplete_logical_model():
                try:
                    if wiring.get_autocomplete_ollama_model():
                        ids.append(str(wiring.runtime.autocomplete_model_logical_id))
                except Exception:
                    pass
            build_rows = _openai_build_model_rows(wiring)
            ids.extend(str(r["id"]) for r in build_rows if r.get("id"))
            return jsonify(anthropic_models_list_payload(ids))

        return jsonify({"object": "list", "data": _openai_model_rows(wiring)})

    @bp.route("/v1/models/<path:model_id>", methods=["GET"])
    def retrieve_model(model_id: str):
        requested = str(model_id or "").strip()
        if not requested:
            return _openai_error_response("model is required", "invalid_request_error", 400)
        for row in _openai_model_rows(wiring):
            if str(row.get("id") or "").strip() == requested:
                return jsonify(row)
        # Some IDE clients probe the manually configured concrete upstream tag
        # instead of a build id. Return the same vision-capable compatibility
        # surface so they do not strip image attachments before proxy routing.
        row = _openai_client_capability_model_row(requested)
        row["metadata"] = {"ollama_model": requested, "synthetic": True}
        return jsonify(row)

    def _sse_lines_from_openai_response(resp: Response):
        buf = b""
        for piece in resp.iter_encoded():
            buf += piece
            while b"\n" in buf:
                idx = buf.index(b"\n")
                line, buf = buf[: idx + 1], buf[idx + 1 :]
                yield line.decode("utf-8", errors="replace")
        if buf:
            yield buf.decode("utf-8", errors="replace")

    @bp.route("/v1/messages", methods=["POST"])
    def anthropic_messages():
        raw = request.get_json(force=True, silent=True) or {}
        if not isinstance(raw, dict):
            return (
                jsonify(
                    {
                        "type": "error",
                        "error": {
                            "type": "invalid_request_error",
                            "message": "JSON body required",
                        },
                    }
                ),
                400,
            )
        openai_body = anthropic_messages_request_to_openai_body(raw)
        default_model = str(openai_body.get("model") or "")
        result = run_chat_completions(wiring, body_override=openai_body)
        if isinstance(result, tuple):
            resp, code = result[0], result[1] if len(result) > 1 else 200
        else:
            resp, code = result, 200
        if code != 200:
            return result
        if resp.mimetype == "text/event-stream":

            def gen():
                yield from iter_anthropic_sse_from_openai_sse_lines(
                    _sse_lines_from_openai_response(resp),
                    default_model=default_model,
                )

            return Response(
                gen(),
                mimetype="text/event-stream",
                status=200,
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        oa = resp.get_json(silent=True)
        if not isinstance(oa, dict):
            return resp
        return jsonify(openai_chat_completion_to_anthropic_message(oa))

    @bp.route("/v1/chat/completions", methods=["POST"])
    def chat_completions():
        raw = request.get_json(force=True, silent=True) or {}
        inbound_request_id = _inbound_request_id_from_headers()
        if isinstance(raw, dict):
            tools = raw.get("tools")
            _V1_LOG.info(
                "v1.chat_completions.request",
                extra={
                    "endpoint": "/v1/chat/completions",
                    "stream": bool(raw.get("stream", False)),
                    "tools_count": len(tools) if isinstance(tools, list) else 0,
                    "tool_choice": raw.get("tool_choice"),
                    "requested_model": raw.get("model"),
                    "trace_id": inbound_request_id,
                },
            )
            body = _with_proxy_trace_meta(
                raw,
                {
                    "proxy_v1_route": "/v1/chat/completions",
                    "incoming_request_id": inbound_request_id,
                },
            )
            return run_chat_completions(wiring, body_override=body)
        return run_chat_completions(wiring)

    @bp.route("/v1/responses", methods=["POST"])
    def responses():
        raw = request.get_json(force=True, silent=True) or {}
        inbound_request_id = _inbound_request_id_from_headers()
        if not isinstance(raw, dict):
            return jsonify({"error": {"message": "JSON body required", "type": "invalid_request_error"}}), 400
        _inp = raw.get("input")
        _input_summary: dict[str, Any] = {
            "input_is_str": isinstance(_inp, str),
            "input_list_len": len(_inp) if isinstance(_inp, list) else 0,
        }
        if isinstance(_inp, list):
            _types: list[str] = []
            for _it in _inp[:30]:
                if isinstance(_it, dict):
                    _types.append(str(_it.get("type") or _it.get("role") or "unknown"))
                else:
                    _types.append(type(_it).__name__)
            _input_summary["input_item_types_head"] = _types
        _V1_LOG.info(
            "v1.responses.request",
            extra={
                "endpoint": "/v1/responses",
                "stream": bool(raw.get("stream", False)),
                "tools_count": len(raw.get("tools")) if isinstance(raw.get("tools"), list) else 0,
                "tool_choice": raw.get("tool_choice"),
                "requested_model": raw.get("model"),
                "trace_id": inbound_request_id,
                "previous_response_id": raw.get("previous_response_id") or "",
                **_input_summary,
            },
        )
        responses_chain_id = _responses_chain_id_for_request(raw, inbound_request_id)
        oa_body, wants_stream, diag = _responses_request_to_openai_chat_body(raw)
        oa_body = _with_proxy_trace_meta(
            oa_body,
            {
                "incoming_request_id": inbound_request_id,
                "trace_chain_id": responses_chain_id,
                "responses_previous_response_id": raw.get("previous_response_id") or "",
            },
        )
        _V1_LOG.info(
            "v1.responses.normalized_tools",
            extra={
                "endpoint": "/v1/responses",
                "tools_count_raw": diag.get("tools_count_raw"),
                "tools_count_normalized": diag.get("tools_count_normalized"),
                "tools_types_raw": diag.get("tools_types_raw"),
                "tools_types_dropped": diag.get("tools_types_dropped"),
                "tools_types_normalized": diag.get("tools_types_normalized"),
                "tool_choice_raw": diag.get("tool_choice_raw"),
                "tool_choice_normalized": diag.get("tool_choice_normalized"),
                "trace_id": inbound_request_id,
            },
        )
        if int(diag.get("tools_count_raw") or 0) > 0 and int(diag.get("tools_count_normalized") or 0) == 0:
            _V1_LOG.warning(
                "v1.responses.tools_all_dropped",
                extra={
                    "endpoint": "/v1/responses",
                    "tools_types_raw": diag.get("tools_types_raw"),
                    "tools_types_dropped": diag.get("tools_types_dropped"),
                    "reason": "all tools unsupported for function bridge",
                },
            )
            with contextlib.suppress(Exception):
                wiring.log_webui_error(
                    "rag_routes.responses_tools_normalization",
                    RuntimeError("all tools unsupported for function bridge"),
                    {
                        "stage": "responses_tools_normalization",
                        "tools_types_raw": diag.get("tools_types_raw"),
                        "tools_types_dropped": diag.get("tools_types_dropped"),
                    },
                )
        result = run_chat_completions(wiring, body_override=oa_body)
        if isinstance(result, tuple):
            resp, code = result[0], result[1] if len(result) > 1 else 200
        else:
            resp, code = result, 200
        if code != 200:
            return result
        oa_json = resp.get_json(silent=True)
        if not isinstance(oa_json, dict):
            return resp
        out, assistant_tail = _chat_completion_to_responses_json(
            oa_json,
            requested_model=str(raw.get("model") or ""),
            raw_request=raw,
        )
        history_seed = list(oa_body.get("messages") or [])
        history_seed.extend(assistant_tail)
        _responses_history_put(str(out.get("id") or ""), history_seed)
        _responses_chain_id_put(str(out.get("id") or ""), responses_chain_id)
        if wants_stream:
            return _responses_sse_payload(out)
        return jsonify(out)

    @bp.route("/v1/files/apply-edit", methods=["POST"])
    def apply_file_edit():
        return run_apply_file_edit(wiring)

    @bp.route("/v1/external-docs/ingest", methods=["POST"])
    def external_docs_ingest():
        return run_external_docs_ingest(wiring)

    return bp


__all__ = [
    "_chat_completion_to_responses_json",
    "_chat_message_to_responses_output_items",
    "_inbound_request_id_from_headers",
    "_openai_build_model_rows",
    "_openai_client_capability_model_row",
    "_openai_error_response",
    "_openai_model_rows",
    "_post_body_is_openai_completions_shape",
    "_RESPONSES_CHAIN_IDS",
    "_RESPONSES_HISTORY",
    "_RESPONSES_HISTORY_MAX",
    "_responses_chain_id_for_request",
    "_responses_chain_id_put",
    "_responses_history_put",
    "_responses_input_to_openai_messages",
    "_responses_normalize_tools",
    "_responses_request_to_openai_chat_body",
    "_responses_sse_payload",
    "_with_proxy_trace_meta",
    "create_v1_blueprint",
]

