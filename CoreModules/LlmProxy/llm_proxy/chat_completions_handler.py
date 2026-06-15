"""OpenAI /v1/chat/completions handler."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

try:
    from chironai_rag.consumers import RAG_COLLECTION_APP_SETTING
except ImportError:
    RAG_COLLECTION_APP_SETTING = "rag_collection"

from flask import Response, jsonify, request

from api.http.proxy_trace import set_response_artifacts
from application.rag.proxy_settings_contract import (
    resolve_fetch_web_knowledge,
    resolve_rag_collection,
)
from llm_proxy.chat_completions_gemini_native import (
    _interpolate_native_tools_for_gemini,
    _preflight_native_tool_messages,
    _preflight_native_tools_payload,
    _resolve_proxy_db_path_from_wiring,
)
from llm_proxy.chat_completions_handler_helpers import (
    apply_selected_rerank_model as _apply_selected_rerank_model,
)
from llm_proxy.chat_completions_handler_helpers import (
    build_forced_think_value as _build_forced_think_value,
)
from llm_proxy.chat_completions_handler_helpers import (
    load_proxy_settings_and_model as _load_proxy_settings_and_model,
)
from llm_proxy.chat_completions_handler_helpers import (
    log_rag_error as _log_rag_error,
)
from llm_proxy.chat_completions_handler_helpers import (
    log_rag_error_private as _log_rag_error_private,
)
from llm_proxy.chat_completions_handler_helpers import (
    rag_request_completed_payload as _rag_request_completed_payload,
)
from llm_proxy.chat_completions_legacy_tool_stream import (
    LegacyToolStreamContext,
    is_legacy_tool_stream_mode,
    try_build_legacy_tool_stream_response,
)
from llm_proxy.chat_completions_messages import (
    _normalize_request_messages,
)
from llm_proxy.chat_completions_native_tools_nonstream import (
    NativeToolsNonStreamContext,
    try_build_native_tools_nonstream_response,
)
from llm_proxy.chat_completions_native_tools_prep import (
    analyze_tool_turn_state,
    resolve_native_tools_policy,
)
from llm_proxy.chat_completions_nonstream_response import (
    StandardNonStreamContext,
    build_standard_nonstream_response,
)
from llm_proxy.chat_completions_ollama_proxy import (
    _append_trace_warning,
    _apply_trace_response_text_fields,
    _build_rag_collection_issue,
    _effective_max_agent_steps,
    _effective_num_ctx,
    _effective_num_predict,
    _effective_rag_collection_name,
    _input_budget_from_context,
    _trace_ollama_messages_for_ui,
    effective_ollama_think_from_body,
)
from llm_proxy.chat_completions_ollama_proxy import (
    ollama_messages_have_images as _ollama_messages_have_images,
)
from llm_proxy.chat_completions_ollama_proxy import (
    resolved_ollama_chat_url as _resolved_ollama_chat_url,
)
from llm_proxy.chat_completions_ollama_proxy import (
    vision_fallback_preferences as _vision_fallback_preferences,
)
from llm_proxy.chat_completions_rag_orchestration import (
    resolve_project_context_collections,
    resolve_skip_rag_retrieval,
    run_chat_rag_pipeline,
)
from llm_proxy.chat_completions_rag_prep import (
    apply_proxy_context_char_limits as _apply_proxy_context_char_limits,
)
from llm_proxy.chat_completions_rag_prep import (
    build_rag_metadata_for_response,
)
from llm_proxy.chat_completions_request_parsing import (
    resolve_trace_chain_id as _resolve_trace_chain_id,
)
from llm_proxy.chat_completions_request_parsing import (
    truthy_body_flag as _truthy_body_flag,
)
from llm_proxy.chat_completions_response_helpers import (
    record_reasoning_token_estimates as _record_reasoning_token_estimates,
)
from llm_proxy.chat_completions_response_helpers import (
    tool_loop_limit_final_message as _tool_loop_limit_final_message,
)
from llm_proxy.chat_completions_response_helpers import (
    with_initial_system_message as _with_initial_system_message,
)
from llm_proxy.chat_completions_run_phases import (
    _new_chat_trace_dict,
    _tool_loop_needs_finalize_nudge,
)
from llm_proxy.chat_completions_sse_generators import (
    NativeToolsStreamContext,
    StandardStreamContext,
    ToolLimitStreamContext,
    iter_native_tools_sse_stream,
    iter_standard_sse_stream,
    iter_tool_limit_sse_stream,
)
from llm_proxy.chat_completions_streaming import (
    SSE_MIMETYPE as _SSE_MIMETYPE,
)
from llm_proxy.chat_completions_streaming import (
    SSE_RESPONSE_HEADERS as _SSE_RESPONSE_HEADERS,
)
from llm_proxy.chat_completions_trace_persistence import (
    build_proxy_request_log_metadata,
)
from llm_proxy.chat_completions_trace_request import (
    build_chat_trace_request_dict,
    enrich_chat_trace_request,
)
from llm_proxy.chat_completions_upstream_budget import (
    _ollama_message_content_str,
    compact_upstream_messages_for_budget,
)
from llm_proxy.contracts import LlmProxyWiring
from llm_proxy.ollama_compat import (
    caps_supports_thinking,
    caps_supports_vision,
    find_cached_ollama_vision_model,
    get_cached_ollama_capabilities,
    ollama_tools_from_openai,
    openai_tool_choice_means_none,
)
from llm_proxy.tool_helpers import (
    _build_tool_json_instruction,
    _client_files_snippet,
    _client_selection_snippet,
    _extract_file_path_from_user_text,
    _get_tool_by_name,
    _select_edit_tool_name,
    _tool_schema_accepts_content,
    _workspace_selection_snippet,
)

_RAG_LOG = logging.getLogger("llm_proxy")


def run_chat_completions(
    w: LlmProxyWiring, *, body_override: dict[str, Any] | None = None
) -> Response | tuple[Response, int]:
    b = w.base
    prefix = b.prefix
    suffix = b.suffix
    webui_dir = b.webui_dir
    system_prefix = b.system_prefix
    system_suffix = b.system_suffix
    context_chunk_chars = b.context_chunk_chars
    context_total_chars = b.context_total_chars
    confidence_threshold = b.confidence_threshold
    ollama_model = b.ollama_model
    log_preview = b.log_preview
    rag_repo = b.rag_repo
    embed_provider = b.embed_provider
    rerank_client = b.rerank_client
    chat_client = b.chat_client

    start_time = time.time()
    user_query = ""
    rag_context_data = None
    latency_ms = 0
    prompt_tokens_approx = 0
    completion_tokens_approx = 0
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    trace = _new_chat_trace_dict(trace_id=trace_id)
    proxy_db_path = _resolve_proxy_db_path_from_wiring(w)
    w.set_current_trace(trace)

    try:
        from api.http.llm_runtime_access import resolve_llm_runtime

        extension_manager = getattr(w, "extension_manager", None)
        if extension_manager is not None:
            resolve_llm_runtime(extension_manager=extension_manager, sync_bootstrap=True)
    except Exception as exc:
        _RAG_LOG.warning("LLM runtime preflight before chat completions failed: %s", exc)

    try:
        if body_override is not None:
            body = dict(body_override)
        else:
            body = request.get_json(force=True, silent=True) or {}
    except Exception as e:
        w.log_webui_error("rag_routes.chat_completions", e, {"stage": "parse_body"})
        _log_rag_error("parse_body", e)
        return jsonify({"error": "Invalid JSON"}), 400
    messages = _normalize_request_messages(body)
    if not messages:
        return jsonify({"error": "messages is required"}), 400
    body["messages"] = messages
    _proxy_trace_meta: dict[str, Any] | None = None
    _raw_trace_meta = body.pop("_proxy_trace_meta", None)
    if isinstance(_raw_trace_meta, dict):
        _proxy_trace_meta = dict(_raw_trace_meta)
    w.set_proxy_status(w.status_rag_search)

    proxy_settings, proxy_model_setting = _load_proxy_settings_and_model(w.get_settings_repository)

    stream = body.get("stream", False)
    chat_max_tokens: int | None = None
    _mt_raw = body.get("max_tokens")
    if _mt_raw is not None:
        try:
            _mt_n = int(_mt_raw)
            if _mt_n > 0:
                chat_max_tokens = _mt_n
        except (TypeError, ValueError):
            pass
    raw_model = body.get("model")
    if raw_model is None or not str(raw_model).strip():
        w.set_proxy_status(w.status_idle)
        return jsonify(
            {
                "error": (
                    "model is required: use an LLM Proxy build id, a concrete Ollama model tag, "
                    "or ChironAI-Autocomplete when autocomplete is configured."
                ),
            }
        ), 400
    requested_model = str(raw_model).strip()
    rt = w.runtime

    build_extra_options: dict[str, Any] = {}
    dumb_build_pipeline = False
    active_build: dict[str, Any] | None = None
    try:
        from application.llm_proxy_builds import (
            LLM_PROXY_BUILDS_APP_KEY,
            build_ollama_options,
            find_build_by_id,
            load_builds_json,
            merge_build_into_proxy_settings,
        )

        _repo_b = w.get_settings_repository()
        _builds_raw = _repo_b.get_app_setting(LLM_PROXY_BUILDS_APP_KEY)
        _all_builds = load_builds_json(_builds_raw)
        active_build = find_build_by_id(_all_builds, str(requested_model or "").strip())
    except Exception:
        active_build = None

    if active_build and str(active_build.get("backend") or "").strip().lower() in ("dumb", "rag_fusion"):
        proxy_settings = merge_build_into_proxy_settings(proxy_settings, active_build)
        _om_b = str(active_build.get("model") or "").strip() or str(active_build.get("ollama_model") or "").strip()
        if _om_b:
            proxy_model_setting = _om_b
        build_extra_options = build_ollama_options(active_build)
        if active_build.get("temperature") is not None:
            try:
                build_extra_options["temperature"] = float(active_build["temperature"])
            except (TypeError, ValueError):
                pass
        if active_build.get("top_p") is not None:
            try:
                build_extra_options["top_p"] = float(active_build["top_p"])
            except (TypeError, ValueError):
                pass
        dumb_build_pipeline = True
        _rl_b = str(active_build.get("reasoning_level") or "").strip()
        if _rl_b and not body.get("reasoning_level") and not body.get("reasoning"):
            body["reasoning_level"] = _rl_b

    build_sse_streaming = True
    if dumb_build_pipeline and active_build:
        build_sse_streaming = active_build.get("sse_streaming", True) is not False

    def ollama_options_overlay() -> dict[str, Any] | None:
        merged: dict[str, Any] = {**build_extra_options}
        if chat_max_tokens is not None:
            build_np = build_extra_options.get("num_predict")
            try:
                build_np_int = int(build_np)
            except (TypeError, ValueError):
                build_np_int = 0
            merged["num_predict"] = min(chat_max_tokens, build_np_int) if build_np_int > 0 else chat_max_tokens
        return merged if merged else None

    effective_num_predict = _effective_num_predict(
        chat_client,
        build_extra_options,
        chat_max_tokens,
    )
    effective_num_ctx = _effective_num_ctx(chat_client, build_extra_options)
    input_budget = _input_budget_from_context(
        num_ctx=effective_num_ctx,
        num_predict=effective_num_predict,
    )

    private_build = bool(dumb_build_pipeline and active_build and bool(active_build.get("private")))
    if private_build:
        w.set_current_trace(None)

    def publish_trace(tr: dict[str, Any]) -> None:
        if private_build:
            w.set_current_trace(None)
        else:
            w.set_current_trace(tr)

    def publish_response_artifacts(
        *,
        visible_content: str,
        reasoning_content: str = "",
        final_content: str = "",
    ) -> None:
        if private_build:
            return
        req = trace.get("request") if isinstance(trace.get("request"), dict) else {}
        set_response_artifacts(
            trace_id=str(trace.get("trace_id") or "").strip() or None,
            client_request_id=str(req.get("client_request_id") or "").strip() or None,
            visible_content=visible_content,
            reasoning_content=reasoning_content,
            final_content=final_content,
        )

    autocomplete_id = rt.autocomplete_model_logical_id
    is_autocomplete = requested_model == autocomplete_id
    proxy_autocomplete_ollama: str | None = None
    tools = body.get("tools") if isinstance(body.get("tools"), list) else []
    tool_choice = body.get("tool_choice")
    tool_choice_effective = tool_choice if tool_choice not in (None, "") else "auto"
    if openai_tool_choice_means_none(tool_choice):
        tool_choice_effective = "none"
    testing_disable_rerank = bool(body.get("testing_disable_rerank"))
    explicit_reasoning = body.get("reasoning_level") or body.get("reasoning")
    if dumb_build_pipeline and "include_rag_metadata" not in body:
        include_rag_metadata = bool(proxy_settings.get("include_rag_metadata", False))
    else:
        include_rag_metadata = bool(body.get("include_rag_metadata", False))
    include_reasoning_content = _truthy_body_flag(body.get("include_reasoning_content"))

    def proxy_backend_tag() -> str:
        if is_autocomplete:
            return "autocomplete"
        if dumb_build_pipeline:
            return "rag_fusion"
        return "direct"

    def persist_proxy_request_log(
        *,
        message: str,
        response_preview: str,
        latency_ms_value: int,
        trace_payload: dict[str, Any],
        stream_value: bool,
        include_rag_fields: bool,
        include_token_fields: bool,
        prompt_tokens_value: int | None = None,
        completion_tokens_value: int | None = None,
        total_tokens_value: int | None = None,
        ollama_chat_stream: bool | None = None,
        sse_single_chunk: bool = False,
        extra_metadata: dict[str, Any] | None = None,
        warn_label: str,
    ) -> None:
        if private_build:
            return
        try:
            session_manager = w.get_session_manager()
            session_manager.get_or_create_session("proxy")
            logs_repo = w.get_logs_repository()
            metadata = build_proxy_request_log_metadata(
                user_query=user_query,
                response_preview=response_preview,
                trace_id=trace_id,
                use_model=use_model,
                latency_ms_value=latency_ms_value,
                trace_payload=trace_payload,
                stream_value=stream_value,
                is_autocomplete=is_autocomplete,
                requested_model=requested_model,
                proxy_backend=proxy_backend_tag(),
                include_rag_fields=include_rag_fields,
                rag_context_data=rag_context_data,
                rag_timings=rag_timings,
                include_token_fields=include_token_fields,
                prompt_tokens_value=prompt_tokens_value,
                completion_tokens_value=completion_tokens_value,
                total_tokens_value=total_tokens_value,
                ollama_chat_stream=ollama_chat_stream,
                sse_single_chunk=sse_single_chunk,
                extra_metadata=extra_metadata,
            )
            logs_repo.add_log(
                session_id="proxy",
                level="INFO",
                message=message,
                source="proxy",
                metadata=metadata,
            )
        except Exception as e:
            _RAG_LOG.warning("Failed to log proxy %s request to database: %s", warn_label, e)

    force_rag = bool(body.get("force_rag"))
    if is_autocomplete:
        force_rag = False
        tools = []
        body["tools"] = []
        tool_choice_effective = "none"
    has_tool_result, last_tool_content, tool_result_indicates_failure, post_tool_success_turn = (
        analyze_tool_turn_state(messages)
    )

    if is_autocomplete:
        proxy_autocomplete_ollama = w.get_autocomplete_ollama_model()
        if not proxy_autocomplete_ollama:
            w.set_proxy_status(w.status_idle)
            return jsonify(
                {
                    "error": (
                        "LLM Proxy autocomplete is not configured: choose a concrete Ollama model "
                        "for autocomplete in WebUI (LLM Proxy → Autocomplete), or set "
                        "LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL."
                    ),
                }
            ), 400

    fetch_web_knowledge, fetch_web_knowledge_source = resolve_fetch_web_knowledge(
        request_value=body.get("fetch_web_knowledge"),
        proxy_settings=proxy_settings,
        is_autocomplete=bool(is_autocomplete),
    )

    _get_rag_prompt = w.get_rag_prompt_prefix_suffix
    rag_prompt_file_exists = w.rag_prompt_file_exists

    use_prompt_template_enabled = proxy_settings.get("use_prompt_template", True) is not False
    proxy_prompt_name_required: str | None = None
    if system_prefix is None:
        if use_prompt_template_enabled:
            _pn = str(body.get("prompt_name") or "").strip() or str(proxy_settings.get("prompt_name") or "").strip()
            if not _pn or not rag_prompt_file_exists(_pn):
                w.set_proxy_status(w.status_idle)
                return jsonify(
                    {
                        "error": (
                            "LLM Proxy is not configured: choose a valid Prompt template in WebUI "
                            "(LLM Proxy → builds or saved proxy settings). The file prompts/<name>.md must exist."
                        ),
                        "detail": f"prompt_name={_pn!r}" if _pn else "prompt_name is empty",
                    }
                ), 400
            proxy_prompt_name_required = _pn
        if dumb_build_pipeline and not proxy_model_setting:
            w.set_proxy_status(w.status_idle)
            return jsonify(
                {
                    "error": "Dumb build is missing model; edit the build in LLM Proxy (builds).",
                }
            ), 400

    last_user = w.last_user_content(messages)
    user_query = last_user  # Store for logging
    selected_edit_tool_name = _select_edit_tool_name(tools, user_query)
    selected_edit_tool = _get_tool_by_name(tools, selected_edit_tool_name) if selected_edit_tool_name else None
    selected_tool_write_capable = _tool_schema_accepts_content(selected_edit_tool)
    # If the client omitted `tools` entirely but referenced a file, assume an IDE-side `edit_file`
    # tool exists (Zed supports it) and allow emitting tool_calls anyway.
    if (not tools) and (tool_choice_effective != "none"):
        user_text = user_query or last_user or ""
        if _extract_file_path_from_user_text(user_text):
            selected_edit_tool_name = "edit_file"
            selected_edit_tool = None
            selected_tool_write_capable = True
    effective_max_agent_steps = _effective_max_agent_steps(active_build)
    _native_tools_policy = resolve_native_tools_policy(
        messages,
        tools,
        tool_choice_effective,
        effective_max_agent_steps=effective_max_agent_steps,
    )
    tools = _native_tools_policy.tools
    tool_choice_effective = _native_tools_policy.tool_choice_effective
    use_native_tools = _native_tools_policy.use_native_tools
    tool_loop_stats = _native_tools_policy.tool_loop_stats
    tool_loop_limit_reached = _native_tools_policy.tool_loop_limit_reached
    context_length = len(last_user.split())
    if system_prefix is not None:
        effective_prefix = prefix
        effective_suffix = suffix
    elif use_prompt_template_enabled:
        effective_prefix, effective_suffix = _get_rag_prompt(proxy_prompt_name_required)
    else:
        effective_prefix, effective_suffix = "", ""
    effective_context_chunk_chars = context_chunk_chars
    effective_context_total_chars = context_total_chars
    effective_confidence_threshold = confidence_threshold
    effective_rag_repo = rag_repo
    effective_embed_provider = embed_provider
    effective_base_rerank_client = rerank_client
    if is_autocomplete:
        effective_ollama_model = proxy_autocomplete_ollama or ""
    elif dumb_build_pipeline:
        effective_ollama_model = proxy_model_setting or ollama_model
    else:
        effective_ollama_model = requested_model
    reasoning_level = w.determine_reasoning_level(
        last_user, context_length, effective_ollama_model, explicit_reasoning
    )
    reasoning_for_prompt = reasoning_level

    actual_model = (
        effective_ollama_model if dumb_build_pipeline or is_autocomplete else requested_model
    )

    trace_chain_id, trace_chain_source = _resolve_trace_chain_id(
        client_request_id=body.get("client_request_id"),
        proxy_trace_meta=_proxy_trace_meta,
    )
    trace["request"] = build_chat_trace_request_dict(
        requested_model=requested_model,
        actual_model=actual_model,
        stream=bool(stream),
        build_sse_streaming=build_sse_streaming,
        chat_max_tokens=chat_max_tokens,
        effective_num_predict=effective_num_predict,
        effective_num_ctx=effective_num_ctx,
        include_rag_metadata=bool(include_rag_metadata),
        tools=tools,
        selected_edit_tool_name=selected_edit_tool_name,
        selected_edit_tool=selected_edit_tool,
        tool_choice=tool_choice,
        tool_choice_effective=tool_choice_effective,
        has_tool_result=bool(has_tool_result),
        tool_result_indicates_failure=bool(tool_result_indicates_failure),
        post_tool_success_turn=bool(post_tool_success_turn),
        last_tool_content=last_tool_content,
        force_rag=bool(force_rag),
        fetch_web_knowledge=bool(fetch_web_knowledge),
        fetch_web_knowledge_source=fetch_web_knowledge_source,
        explicit_reasoning=explicit_reasoning,
        reasoning_level=reasoning_level,
        reasoning_for_prompt=reasoning_for_prompt,
        user_query=user_query,
        is_autocomplete=bool(is_autocomplete),
        testing_disable_rerank=bool(testing_disable_rerank),
        client_request_id=body.get("client_request_id"),
    )
    enrich_chat_trace_request(
        trace,
        input_budget=input_budget,
        effective_max_agent_steps=effective_max_agent_steps,
        tool_loop_limit_reached=tool_loop_limit_reached,
        trace_chain_id=trace_chain_id,
        trace_chain_source=trace_chain_source,
        tool_loop_stats=tool_loop_stats,
        proxy_trace_meta=_proxy_trace_meta,
        body=body,
        append_trace_warning=_append_trace_warning,
    )

    # IDE-independent mode: do not fail fast solely on schema checks.
    # Some clients expose incomplete tool schemas but still accept write payloads at runtime.

    # Optional project_context: frameworks list -> fresh collection names for RAG filter
    project_context = body.get("project_context")
    _project_ctx = resolve_project_context_collections(
        w=w,
        fetch_web_knowledge=bool(fetch_web_knowledge),
        project_context=project_context,
    )
    project_fresh_collection_names = _project_ctx.project_fresh_collection_names
    needs_refresh = list(_project_ctx.needs_refresh)

    # Resolve collection in priority order:
    # 1) request body collection_name
    # 2) app_settings.rag_collection
    # 3) proxy_settings.rag_collection (backward-compatible / single blob settings)
    # 4) default wiring (collection file/config) when none are set
    try:
        settings_repo = w.get_settings_repository()
    except Exception:
        settings_repo = None
    if settings_repo is not None:
        request_collection, collection_source = resolve_rag_collection(
            request_collection=(body.get("collection_name") or "").strip() or None,
            settings_repo=settings_repo,
            proxy_settings=proxy_settings,
            app_key=RAG_COLLECTION_APP_SETTING,
        )
    else:
        request_collection = (body.get("collection_name") or "").strip() or None
        collection_source = "request" if request_collection else "default"
    if request_collection and not is_autocomplete:
        req_params, req_deps = w.get_rag_answer_params(
            webui_dir=webui_dir,
            collection_name=request_collection,
        )
        if system_prefix is not None:
            effective_prefix = system_prefix
            effective_suffix = system_suffix if system_suffix is not None else req_params.system_suffix
        elif not use_prompt_template_enabled:
            effective_prefix = ""
            effective_suffix = ""
        effective_context_chunk_chars = req_params.context_chunk_chars
        effective_context_total_chars = req_params.context_total_chars
        effective_confidence_threshold = req_params.confidence_threshold
        effective_ollama_model = req_params.model_name
        effective_rag_repo = req_deps.rag_repo
        # Keep wiring runtime-backed embed/rerank (collection override must not drop extension runtime).
        effective_embed_provider = embed_provider
        effective_base_rerank_client = rerank_client
        if dumb_build_pipeline and proxy_model_setting:
            effective_ollama_model = proxy_model_setting
        actual_model = (
            effective_ollama_model if dumb_build_pipeline or is_autocomplete else requested_model
        )
        trace["request"]["actual_model"] = actual_model
        trace["request"]["collection_name"] = request_collection
        trace["request"]["collection_source"] = collection_source
        trace["request"]["legacy_collection_fallback_used"] = collection_source == "proxy_settings.rag_collection"
    else:
        trace["request"]["collection_source"] = "default"

    if is_autocomplete:
        effective_ollama_model = proxy_autocomplete_ollama or effective_ollama_model
    if dumb_build_pipeline and proxy_model_setting:
        effective_ollama_model = proxy_model_setting
    actual_model = (
        effective_ollama_model if dumb_build_pipeline or is_autocomplete else requested_model
    )
    trace["request"]["actual_model"] = actual_model

    effective_collection_name = _effective_rag_collection_name(effective_rag_repo)
    trace["rag"]["collection_name"] = effective_collection_name
    trace["rag"]["collection_source"] = trace["request"].get("collection_source") or collection_source
    if not is_autocomplete and not private_build:
        collection_issue = _build_rag_collection_issue(
            collection_name=effective_collection_name,
            collection_source=str(trace["rag"].get("collection_source") or "default"),
            qdrant_url=w.get_qdrant_url(),
        )
        if collection_issue:
            trace["rag"]["collection_issue"] = collection_issue
            _append_trace_warning(trace, str(collection_issue.get("code") or "rag_collection_issue"))
            publish_trace(trace)

    # Collection resolution can reload proxy_settings from DB and drop the dumb-build merge;
    # re-apply build overlay so per-build RAG limits and rag_collection stay authoritative.
    if dumb_build_pipeline and active_build:
        try:
            from application.llm_proxy_builds import merge_build_into_proxy_settings as _merge_build_ps

            proxy_settings = _merge_build_ps(dict(proxy_settings), active_build)
        except Exception:
            pass

    effective_context_chunk_chars, effective_context_total_chars, effective_rag_top_k = (
        _apply_proxy_context_char_limits(
            proxy_settings,
            effective_context_chunk_chars=effective_context_chunk_chars,
            effective_context_total_chars=effective_context_total_chars,
        )
    )
    trace["request"]["effective_context_chunk_chars"] = effective_context_chunk_chars
    trace["request"]["effective_context_total_chars"] = effective_context_total_chars
    if effective_rag_top_k is not None:
        trace["request"]["rag_top_k"] = effective_rag_top_k

    # Keep embed model in sync with WebUI setting for /v1 path as well.
    # This avoids accidental model="" calls to /api/embed when env defaults are empty.
    try:
        settings_repo = w.get_settings_repository()
        selected_embed_model = str(settings_repo.get_app_setting("rag_embed_model") or "").strip()
        current_embed_model = str(
            getattr(effective_embed_provider, "_model", None)
            or getattr(effective_embed_provider, "model", None)
            or ""
        ).strip()
        target_embed_model = selected_embed_model or current_embed_model or str(effective_ollama_model or "").strip()
        if target_embed_model:
            if hasattr(effective_embed_provider, "_model"):
                effective_embed_provider._model = target_embed_model
            elif hasattr(effective_embed_provider, "model"):
                effective_embed_provider.model = target_embed_model
            if target_embed_model != current_embed_model:
                trace["request"]["embed_model_override"] = target_embed_model
    except Exception:
        pass

    _ollama_caps: frozenset[str] | None = None
    ollama_chat_url: str | None = None
    try:
        ollama_chat_url = _resolved_ollama_chat_url(chat_client)
        if ollama_chat_url and (effective_ollama_model or "").strip():
            trace["request"]["ollama_capabilities_lookup_url"] = ollama_chat_url
            _ollama_caps = get_cached_ollama_capabilities(
                effective_ollama_model.strip(), ollama_chat_url
            )
    except Exception:
        _ollama_caps = None

    ollama_think = effective_ollama_think_from_body(
        body, effective_ollama_model, capabilities=_ollama_caps
    )
    forced_build_think = _build_forced_think_value(
        body=body,
        active_build=active_build if dumb_build_pipeline else None,
        model_name=effective_ollama_model,
    )
    if forced_build_think is not None:
        ollama_think = forced_build_think
        trace["request"]["ollama_think_source"] = "build.chat_think"
    trace["request"]["ollama_think"] = ollama_think
    if _ollama_caps is not None:
        trace["request"]["ollama_capabilities"] = sorted(_ollama_caps)
    trace["request"]["use_native_tools"] = use_native_tools

    effective_base_rerank_client = _apply_selected_rerank_model(
        effective_base_rerank_client,
        proxy_settings,
        trace,
    )

    # Proxy: do not read settings from DB; rerank is configurable via proxy_rerank_enabled.
    effective_rerank_client = (
        effective_base_rerank_client
        if (w.get_proxy_rerank_enabled() and not testing_disable_rerank)
        else None
    )
    rag_keywords = w.get_rag_required_keywords()

    _skip_rag = resolve_skip_rag_retrieval(
        body=body,
        last_user=last_user,
        tools=tools,
        selected_edit_tool_name=selected_edit_tool_name,
        tool_choice_effective=tool_choice_effective,
        use_native_tools=use_native_tools,
        force_rag=bool(force_rag),
        fetch_web_knowledge=bool(fetch_web_knowledge),
        request_collection=request_collection,
        post_tool_success_turn=post_tool_success_turn,
        is_autocomplete=bool(is_autocomplete),
        dumb_build_pipeline=dumb_build_pipeline,
        proxy_settings=proxy_settings,
    )
    trace["request"]["doc_refactor_intent"] = bool(_skip_rag.doc_refactor_intent)
    trace["request"]["doc_refactor_skip"] = bool(_skip_rag.doc_refactor_skip)
    skip_rag_retrieval = _skip_rag.skip_rag_retrieval
    trace["request"]["skip_rag_retrieval"] = bool(skip_rag_retrieval)

    _rag_pipeline = run_chat_rag_pipeline(
        w=w,
        trace=trace,
        last_user=last_user,
        messages=messages,
        body=body,
        fetch_web_knowledge=bool(fetch_web_knowledge),
        request_collection=request_collection,
        effective_rag_repo=effective_rag_repo,
        effective_embed_provider=effective_embed_provider,
        effective_rerank_client=effective_rerank_client,
        effective_context_chunk_chars=effective_context_chunk_chars,
        effective_context_total_chars=effective_context_total_chars,
        effective_confidence_threshold=float(effective_confidence_threshold),
        effective_rag_top_k=effective_rag_top_k,
        rag_keywords=rag_keywords,
        force_rag=bool(force_rag),
        skip_rag_retrieval=skip_rag_retrieval,
        is_autocomplete=bool(is_autocomplete),
        doc_refactor_skip=bool(_skip_rag.doc_refactor_skip),
        proxy_settings=proxy_settings,
        project_fresh_collection_names=project_fresh_collection_names,
        needs_refresh=needs_refresh,
        private_build=private_build,
        publish_trace=publish_trace,
    )
    rag_ctx_for_log = _rag_pipeline.rag_ctx_for_log
    rag_timings = _rag_pipeline.rag_timings
    rag_context_data = _rag_pipeline.rag_context_data
    web_supplement_text = _rag_pipeline.web_supplement_text

    # Reuse the same RAG context for messages (single RAG call per request)
    rag_ctx = rag_ctx_for_log if (include_rag_metadata and rag_ctx_for_log) else None
    try:
        req = w.rag_question_request_factory(
            messages=messages,
            model=actual_model,  # Use actual_model instead of requested_model
            stream=stream,
            reasoning_level=reasoning_for_prompt,
        )
        ollama_messages, use_model = w.prepare_ollama_messages(
            req,
            effective_rag_repo,
            effective_embed_provider,
            effective_rerank_client,
            effective_prefix,
            effective_suffix,
            effective_context_chunk_chars,
            effective_context_total_chars,
            effective_confidence_threshold,
            effective_ollama_model,
            reasoning_level=reasoning_for_prompt,
            rag_required_keywords=rag_keywords,
            rag_context=rag_ctx_for_log,
            trigger_threshold=None,
            force_rag=force_rag,
            native_tools=use_native_tools,
            web_supplement=web_supplement_text,
        )
        if use_model == autocomplete_id:
            use_model = effective_ollama_model

        if input_budget is not None:
            ollama_messages, compact_diag = compact_upstream_messages_for_budget(
                ollama_messages,
                input_budget,
            )
            if compact_diag.get("compacted") or compact_diag.get("still_over_budget_after_history_compaction"):
                trace["request"]["upstream_context_compaction"] = compact_diag

        trace["ollama"]["model"] = use_model
        trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(ollama_messages)
        trace["ollama"]["think"] = ollama_think
        trace["ollama"]["chat_stream"] = False
        ollama_messages_have_images = _ollama_messages_have_images(ollama_messages)
        image_model_caps: frozenset[str] | None = _ollama_caps
        if ollama_messages_have_images and ollama_chat_url:
            try:
                image_model_caps = get_cached_ollama_capabilities(use_model, ollama_chat_url)
            except Exception:
                image_model_caps = None
            if image_model_caps is not None:
                _ollama_caps = image_model_caps
                trace["request"]["ollama_capabilities"] = sorted(image_model_caps)
            if image_model_caps is not None and not caps_supports_vision(image_model_caps):
                fallback_model = find_cached_ollama_vision_model(
                    ollama_chat_url,
                    preferred_models=_vision_fallback_preferences(active_build),
                )
                if fallback_model and fallback_model != use_model:
                    original_use_model = use_model
                    use_model = fallback_model
                    effective_ollama_model = fallback_model
                    fallback_caps = get_cached_ollama_capabilities(fallback_model, ollama_chat_url)
                    if fallback_caps is not None:
                        image_model_caps = fallback_caps
                        _ollama_caps = fallback_caps
                        trace["request"]["ollama_capabilities"] = sorted(fallback_caps)
                        if ollama_think is not None and not caps_supports_thinking(fallback_caps):
                            ollama_think = None
                            trace["request"]["ollama_think"] = None
                            trace["request"]["vision_fallback_stripped_think"] = True
                    trace["request"]["actual_model"] = use_model
                    trace["request"]["vision_model_fallback"] = {
                        "from": original_use_model,
                        "to": use_model,
                        "reason": "selected_ollama_model_lacks_vision",
                    }
                    trace["ollama"]["model"] = use_model
                    trace["ollama"]["think"] = ollama_think
                    _append_trace_warning(trace, "vision_model_fallback")
        trace["request"]["use_native_tools"] = use_native_tools
        trace["request"]["tool_choice_effective"] = (
            tool_choice_effective
            if isinstance(tool_choice_effective, (str, dict))
            else str(tool_choice_effective)
        )
        trace["request"]["tools_count_effective"] = (
            len(tools) if use_native_tools and tool_choice_effective != "none" else 0
        )
        if use_native_tools and ollama_messages_have_images:
            trace["request"]["native_tools_preserved_for_vision"] = True
        client_visible_model = requested_model if dumb_build_pipeline else use_model

        if tool_loop_limit_reached:
            content = _tool_loop_limit_final_message(trace) or (
                "[Error: max_agent_steps limit reached. Tools were disabled for this turn.]"
            )
            _append_trace_warning(trace, "tool_loop_limit_response_forced")
            latency_ms = int((time.time() - start_time) * 1000)
            _prompt_text = " ".join(
                _ollama_message_content_str(m.get("content"))
                for m in ollama_messages
                if isinstance(m, dict)
            )
            prompt_tokens_approx = max(1, int(len(_prompt_text) / 4))
            completion_tokens_approx = max(1, int(len(content) / 4))
            _total_tokens_approx = prompt_tokens_approx + completion_tokens_approx
            w.set_proxy_status(w.status_idle)
            w.set_latest_request_seconds(time.time() - start_time)
            w.set_latest_request_total_tokens(_total_tokens_approx)
            trace["ollama"]["chat_skipped"] = "tool_loop_limit_reached"
            trace["ollama"]["tokens_estimates"] = {
                "prompt_tokens_estimated": prompt_tokens_approx,
                "completion_tokens_estimated": completion_tokens_approx,
                "total_tokens_estimated": _total_tokens_approx,
            }
            trace["response"] = {
                "latency_ms": latency_ms,
                "tool_calls_count": 0,
            }
            _record_reasoning_token_estimates(trace["response"], "", content)
            _apply_trace_response_text_fields(
                trace["response"],
                visible_content=content,
                reasoning_content="",
                final_content=content,
                log_preview=log_preview,
            )
            trace["steps"].append(
                {
                    "name": "tool_loop_limit_response",
                    "duration_ms": latency_ms,
                    "tokens_in_est": prompt_tokens_approx,
                    "tokens_out_est": completion_tokens_approx,
                }
            )
            publish_response_artifacts(
                visible_content=content,
                reasoning_content="",
                final_content=content,
            )
            publish_trace(trace)
            response_data: dict[str, object] = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                "object": "chat.completion",
                "created": 0,
                "model": client_visible_model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
            }
            if include_rag_metadata and rag_ctx:
                response_data["rag_metadata"] = build_rag_metadata_for_response(rag_ctx)

            if stream:
                rid = str(response_data["id"])

                return Response(
                    iter_tool_limit_sse_stream(
                        ToolLimitStreamContext(
                            response_id=rid,
                            client_visible_model=client_visible_model,
                            content=content,
                            private_build=private_build,
                            user_query=user_query,
                            log_preview=log_preview,
                            latency_ms=latency_ms,
                            trace=trace,
                            prompt_tokens_approx=prompt_tokens_approx,
                            completion_tokens_approx=completion_tokens_approx,
                            total_tokens_approx=_total_tokens_approx,
                            persist_proxy_request_log=persist_proxy_request_log,
                        )
                    ),
                    mimetype=_SSE_MIMETYPE,
                    headers=_SSE_RESPONSE_HEADERS,
                )

            if not private_build:
                persist_proxy_request_log(
                    message=f"Proxy request (tool limit): {user_query[:100]}...",
                    response_preview=content[:log_preview],
                    latency_ms_value=latency_ms,
                    trace_payload=trace,
                    stream_value=False,
                    include_rag_fields=True,
                    include_token_fields=True,
                    prompt_tokens_value=prompt_tokens_approx,
                    completion_tokens_value=completion_tokens_approx,
                    total_tokens_value=_total_tokens_approx,
                    extra_metadata={"tool_loop_limit_response": True},
                    warn_label="tool limit",
                )
            return jsonify(response_data)
    except Exception as e:
        if not private_build:
            w.log_webui_error("rag_routes.chat_completions", e, {"stage": "prepare_rag"})
        _log_rag_error_private("prepare_rag", e, private_build=private_build)
        return jsonify({"error": str(e)}), 500

    if use_native_tools:
        trace["request"]["native_tools"] = True
        native_tools_diag: dict[str, Any] = {}
        native_tools_input = list(tools)
        native_tools_input, interpolation_diag = _interpolate_native_tools_for_gemini(
            native_tools_input,
            model_name=use_model,
        )
        if interpolation_diag:
            native_tools_diag.update(interpolation_diag)
        native_tools_payload, tools_diag = _preflight_native_tools_payload(native_tools_input)
        if tools_diag:
            native_tools_diag.update(tools_diag)
        oll_tools = ollama_tools_from_openai(native_tools_payload)
        native_ollama_messages, messages_diag = _preflight_native_tool_messages(
            ollama_messages,
            model_name=use_model,
            trace_id=trace_id,
            db_path=proxy_db_path,
        )
        if messages_diag:
            native_tools_diag.update(messages_diag)

        native_ollama_messages, compact_diag = compact_upstream_messages_for_budget(
            native_ollama_messages,
            input_budget,
        )
        if compact_diag.get("compacted") or compact_diag.get("still_over_budget_after_history_compaction"):
            native_tools_diag["upstream_context_compaction"] = compact_diag

        native_ollama_messages_for_upstream = native_ollama_messages
        trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(native_ollama_messages_for_upstream)
        trace["ollama"]["tools"] = list(oll_tools) if isinstance(oll_tools, list) else []
        if (
            has_tool_result
            and not tool_result_indicates_failure
            and _tool_loop_needs_finalize_nudge(tool_loop_stats)
        ):
            native_ollama_messages = _with_initial_system_message(
                native_ollama_messages,
                (
                    "You have already completed multiple consecutive tool rounds of the same type. "
                    "Prefer synthesizing the final answer now, and call another tool only if a concrete blocker remains."
                ),
            )
            native_tools_diag["tool_loop_finalize_nudge"] = True
            native_ollama_messages_for_upstream = native_ollama_messages
            trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(native_ollama_messages_for_upstream)
        if native_tools_diag:
            trace["request"]["native_tools_preflight"] = native_tools_diag

        # ------------------------------------------------------------------ #
        #  STREAMING native tools: true token-by-token SSE                    #
        # ------------------------------------------------------------------ #
        if stream and build_sse_streaming:
            w.set_proxy_status(w.status_response)
            trace["request"]["ollama_stream_timeout_disabled"] = True

            return Response(
                iter_native_tools_sse_stream(
                    NativeToolsStreamContext(
                        w=w,
                        trace=trace,
                        private_build=private_build,
                        client_visible_model=client_visible_model,
                        chat_client=chat_client,
                        native_ollama_messages_for_upstream=native_ollama_messages_for_upstream,
                        use_model=use_model,
                        ollama_think=ollama_think,
                        oll_tools=oll_tools,
                        tool_choice_effective=tool_choice_effective,
                        include_reasoning_content=include_reasoning_content,
                        user_query=user_query,
                        trace_id=trace_id,
                        proxy_db_path=proxy_db_path,
                        log_preview=log_preview,
                        start_time=start_time,
                        rag_ctx_for_log=rag_ctx_for_log,
                        rag_timings=rag_timings,
                        requested_model=requested_model,
                        is_autocomplete=is_autocomplete,
                        ollama_options_overlay=ollama_options_overlay,
                        publish_trace=publish_trace,
                        publish_response_artifacts=publish_response_artifacts,
                        persist_proxy_request_log=persist_proxy_request_log,
                        log_rag_error_private=_log_rag_error_private,
                        rag_request_completed_payload=_rag_request_completed_payload,
                    )
                ),
                mimetype=_SSE_MIMETYPE,
                headers=_SSE_RESPONSE_HEADERS,
            )

        return try_build_native_tools_nonstream_response(
            NativeToolsNonStreamContext(
                w=w,
                trace=trace,
                private_build=private_build,
                stream=bool(stream),
                client_visible_model=client_visible_model,
                chat_client=chat_client,
                native_ollama_messages=native_ollama_messages,
                native_ollama_messages_for_upstream=native_ollama_messages_for_upstream,
                use_model=use_model,
                ollama_think=ollama_think,
                oll_tools=oll_tools,
                tool_choice_effective=tool_choice_effective,
                include_reasoning_content=include_reasoning_content,
                include_rag_metadata=bool(include_rag_metadata),
                user_query=user_query,
                trace_id=trace_id,
                proxy_db_path=proxy_db_path,
                log_preview=log_preview,
                start_time=start_time,
                rag_ctx=rag_ctx,
                rag_ctx_for_log=rag_ctx_for_log,
                rag_timings=rag_timings,
                requested_model=requested_model,
                is_autocomplete=is_autocomplete,
                post_tool_success_turn=post_tool_success_turn,
                native_tools_diag=native_tools_diag,
                ollama_options_overlay=ollama_options_overlay,
                publish_trace=publish_trace,
                publish_response_artifacts=publish_response_artifacts,
                persist_proxy_request_log=persist_proxy_request_log,
                log_rag_error_private=_log_rag_error_private,
                rag_request_completed_payload=_rag_request_completed_payload,
            )
        )

    if tools and tool_choice_effective != "none":
        if not post_tool_success_turn:
            tool_json_instruction = _build_tool_json_instruction(
                selected_edit_tool_name, selected_edit_tool
            )
            if tool_json_instruction:
                ollama_messages = _with_initial_system_message(ollama_messages, tool_json_instruction)
            excerpt_sys = _workspace_selection_snippet(user_query or last_user or "").strip()
            if not excerpt_sys:
                excerpt_sys = (
                    _client_selection_snippet(user_query or last_user or "").strip()
                    or _client_files_snippet(user_query or last_user or "").strip()
                )
            if excerpt_sys:
                ollama_messages = _with_initial_system_message(ollama_messages, excerpt_sys)

        if input_budget is not None:
            ollama_messages, compact_diag = compact_upstream_messages_for_budget(
                ollama_messages,
                input_budget,
            )
            if compact_diag.get("compacted") or compact_diag.get("still_over_budget_after_history_compaction"):
                trace["request"]["upstream_context_compaction"] = compact_diag

        trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(ollama_messages)
        trace["ollama"]["model"] = use_model
        publish_trace(trace)

    if is_legacy_tool_stream_mode(
        stream=stream,
        tools=tools,
        tool_choice_effective=tool_choice_effective,
        post_tool_success_turn=post_tool_success_turn,
    ):
        legacy_tool_response = try_build_legacy_tool_stream_response(
            LegacyToolStreamContext(
                w=w,
                trace=trace,
                trace_id=trace_id,
                private_build=private_build,
                client_visible_model=client_visible_model,
                chat_client=chat_client,
                ollama_messages=ollama_messages,
                use_model=use_model,
                ollama_think=ollama_think,
                user_query=user_query,
                log_preview=log_preview,
                start_time=start_time,
                rag_ctx_for_log=rag_ctx_for_log,
                rag_timings=rag_timings,
                requested_model=requested_model,
                is_autocomplete=is_autocomplete,
                selected_edit_tool_name=selected_edit_tool_name,
                selected_edit_tool=selected_edit_tool,
                selected_tool_write_capable=selected_tool_write_capable,
                ollama_options_overlay=ollama_options_overlay,
                publish_trace=publish_trace,
                publish_response_artifacts=publish_response_artifacts,
                persist_proxy_request_log=persist_proxy_request_log,
                log_rag_error_private=_log_rag_error_private,
                rag_request_completed_payload=_rag_request_completed_payload,
            )
        )
        if legacy_tool_response is not None:
            return legacy_tool_response

    if stream and build_sse_streaming:
        w.set_proxy_status(w.status_response)

        return Response(
            iter_standard_sse_stream(
                StandardStreamContext(
                    w=w,
                    trace=trace,
                    trace_id=trace_id,
                    private_build=private_build,
                    client_visible_model=client_visible_model,
                    chat_client=chat_client,
                    ollama_messages=ollama_messages,
                    use_model=use_model,
                    ollama_think=ollama_think,
                    include_reasoning_content=include_reasoning_content,
                    user_query=user_query,
                    log_preview=log_preview,
                    start_time=start_time,
                    rag_ctx_for_log=rag_ctx_for_log,
                    rag_timings=rag_timings,
                    requested_model=requested_model,
                    is_autocomplete=is_autocomplete,
                    ollama_options_overlay=ollama_options_overlay,
                    publish_trace=publish_trace,
                    publish_response_artifacts=publish_response_artifacts,
                    persist_proxy_request_log=persist_proxy_request_log,
                    log_rag_error_private=_log_rag_error_private,
                    rag_request_completed_payload=_rag_request_completed_payload,
                )
            ),
            mimetype=_SSE_MIMETYPE,
            headers=_SSE_RESPONSE_HEADERS,
        )
    return build_standard_nonstream_response(
        StandardNonStreamContext(
            w=w,
            trace=trace,
            private_build=private_build,
            stream=bool(stream),
            build_sse_streaming=build_sse_streaming,
            client_visible_model=client_visible_model,
            chat_client=chat_client,
            ollama_messages=ollama_messages,
            use_model=use_model,
            ollama_think=ollama_think,
            include_reasoning_content=include_reasoning_content,
            include_rag_metadata=bool(include_rag_metadata),
            user_query=user_query,
            trace_id=trace_id,
            log_preview=log_preview,
            start_time=start_time,
            rag_ctx=rag_ctx,
            rag_ctx_for_log=rag_ctx_for_log,
            rag_timings=rag_timings,
            requested_model=requested_model,
            is_autocomplete=is_autocomplete,
            tools=tools,
            tool_choice_effective=tool_choice_effective,
            post_tool_success_turn=post_tool_success_turn,
            selected_edit_tool_name=selected_edit_tool_name,
            selected_edit_tool=selected_edit_tool,
            selected_tool_write_capable=selected_tool_write_capable,
            ollama_options_overlay=ollama_options_overlay,
            publish_trace=publish_trace,
            publish_response_artifacts=publish_response_artifacts,
            persist_proxy_request_log=persist_proxy_request_log,
            log_rag_error_private=_log_rag_error_private,
            rag_request_completed_payload=_rag_request_completed_payload,
        )
    )
