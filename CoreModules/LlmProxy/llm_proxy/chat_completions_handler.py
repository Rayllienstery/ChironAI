"""OpenAI /v1/chat/completions handler."""

from __future__ import annotations

import contextlib
import logging
import time
import uuid
from typing import Any

from flask import Response, jsonify, request

from application.rag.proxy_settings_contract import (
    resolve_fetch_web_knowledge,
    resolve_rag_collection,
)
from core.contracts.rag_api import RAG_COLLECTION_APP_SETTING
from llm_proxy import chat_completions_handler_prepare as _handler_prepare_module
from llm_proxy.chat_completions_gemini_native import (
    _resolve_proxy_db_path_from_wiring,
)
from llm_proxy.chat_completions_handler_closures import (
    build_ollama_options_overlay,
    make_persist_proxy_request_log,
    make_publish_response_artifacts,
    make_publish_trace,
)
from llm_proxy.chat_completions_handler_dispatch import dispatch_response
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
from llm_proxy.chat_completions_handler_prepare import (
    prepare_messages_and_handle_tool_limit,
)
from llm_proxy.chat_completions_messages import (
    _normalize_request_messages,
)
from llm_proxy.chat_completions_native_tools_prep import (
    analyze_tool_turn_state,
    resolve_native_tools_policy,
)
from llm_proxy.chat_completions_ollama_proxy import (
    _append_trace_warning,
    _build_rag_collection_issue,
    _effective_max_agent_steps,
    _effective_num_ctx,
    _effective_num_predict,
    _effective_rag_collection_name,
    _input_budget_from_context,
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
from llm_proxy.chat_completions_request_parsing import (
    resolve_trace_chain_id as _resolve_trace_chain_id,
)
from llm_proxy.chat_completions_request_parsing import (
    truthy_body_flag as _truthy_body_flag,
)
from llm_proxy.chat_completions_response_helpers import (
    tool_loop_limit_final_message as _tool_loop_limit_final_message,
)
from llm_proxy.chat_completions_run_phases import (
    _new_chat_trace_dict,
)
from llm_proxy.chat_completions_trace_request import (
    build_chat_trace_request_dict,
    enrich_chat_trace_request,
)
from llm_proxy.contracts import LlmProxyWiring
from llm_proxy.ollama_compat import (
    find_cached_ollama_vision_model,
    get_cached_ollama_capabilities,
    openai_tool_choice_means_none,
)
from llm_proxy.tool_helpers import (
    _extract_file_path_from_user_text,
    _get_tool_by_name,
    _select_edit_tool_name,
    _tool_schema_accepts_content,
)

_RAG_LOG = logging.getLogger("llm_proxy")

__all__ = [
    "_ollama_messages_have_images",
    "_resolved_ollama_chat_url",
    "_tool_loop_limit_final_message",
    "_vision_fallback_preferences",
    "find_cached_ollama_vision_model",
    "get_cached_ollama_capabilities",
    "run_chat_completions",
]


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
        body = dict(body_override) if body_override is not None else request.get_json(force=True, silent=True) or {}
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
            with contextlib.suppress(TypeError, ValueError):
                build_extra_options["temperature"] = float(active_build["temperature"])
        if active_build.get("top_p") is not None:
            with contextlib.suppress(TypeError, ValueError):
                build_extra_options["top_p"] = float(active_build["top_p"])
        dumb_build_pipeline = True
        _rl_b = str(active_build.get("reasoning_level") or "").strip()
        if _rl_b and not body.get("reasoning_level") and not body.get("reasoning"):
            body["reasoning_level"] = _rl_b

    if active_build and dumb_build_pipeline:
        _build_provider_id = str(active_build.get("provider_id") or "").strip()
        if _build_provider_id:
            try:
                from rag_service.infrastructure.provider_runtime import chat_client_for_provider_id

                chat_client = chat_client_for_provider_id(chat_client, _build_provider_id)
            except Exception as exc:
                _RAG_LOG.warning(
                    "Failed to scope chat client to build provider %s: %s",
                    _build_provider_id,
                    exc,
                )

    build_sse_streaming = True
    if dumb_build_pipeline and active_build:
        build_sse_streaming = active_build.get("sse_streaming", True) is not False

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

    ollama_options_overlay = lambda: build_ollama_options_overlay(build_extra_options, chat_max_tokens)
    publish_trace = make_publish_trace(w, private_build)
    publish_response_artifacts = make_publish_response_artifacts(trace, private_build)

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
                            "(LLM Proxy → builds or saved proxy settings). The prompt template must exist in the prompt store."
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
        except Exception:  # safe: build overlay re-merge best-effort
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
    except Exception:  # safe: embed model override best-effort
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

    rag_ctx = rag_ctx_for_log if (include_rag_metadata and rag_ctx_for_log) else None
    use_model_ref = [actual_model]
    persist_proxy_request_log = make_persist_proxy_request_log(
        w,
        private_build=private_build,
        user_query=user_query,
        trace_id=trace_id,
        trace_chain_id=trace_chain_id,
        is_autocomplete=is_autocomplete,
        requested_model=requested_model,
        dumb_build_pipeline=dumb_build_pipeline,
        rag_context_data=[rag_context_data],
        rag_timings=[rag_timings],
        use_model_ref=use_model_ref,
    )
    try:
        _handler_prepare_module.get_cached_ollama_capabilities = get_cached_ollama_capabilities
        _handler_prepare_module.find_cached_ollama_vision_model = find_cached_ollama_vision_model
        _handler_prepare_module._vision_fallback_preferences = _vision_fallback_preferences
        prepared = prepare_messages_and_handle_tool_limit(
            w=w,
            trace=trace,
            messages=messages,
            stream=stream,
            body=body,
            actual_model=actual_model,
            reasoning_for_prompt=reasoning_for_prompt,
            effective_rag_repo=effective_rag_repo,
            effective_embed_provider=effective_embed_provider,
            effective_rerank_client=effective_rerank_client,
            effective_prefix=effective_prefix,
            effective_suffix=effective_suffix,
            effective_context_chunk_chars=effective_context_chunk_chars,
            effective_context_total_chars=effective_context_total_chars,
            effective_confidence_threshold=effective_confidence_threshold,
            effective_ollama_model=effective_ollama_model,
            rag_keywords=rag_keywords,
            rag_ctx_for_log=rag_ctx_for_log,
            force_rag=force_rag,
            use_native_tools=use_native_tools,
            web_supplement_text=web_supplement_text,
            autocomplete_id=autocomplete_id,
            input_budget=input_budget,
            ollama_think=ollama_think,
            ollama_chat_url=ollama_chat_url,
            _ollama_caps=_ollama_caps,
            active_build=active_build,
            dumb_build_pipeline=dumb_build_pipeline,
            requested_model=requested_model,
            is_autocomplete=is_autocomplete,
            tool_choice_effective=tool_choice_effective,
            tools=tools,
            tool_loop_limit_reached=tool_loop_limit_reached,
            include_rag_metadata=include_rag_metadata,
            include_reasoning_content=include_reasoning_content,
            private_build=private_build,
            user_query=user_query,
            log_preview=log_preview,
            start_time=start_time,
            rag_ctx=rag_ctx,
            rag_timings=rag_timings,
            latency_ms=latency_ms,
            prompt_tokens_approx=prompt_tokens_approx,
            completion_tokens_approx=completion_tokens_approx,
            publish_trace=publish_trace,
            publish_response_artifacts=publish_response_artifacts,
            persist_proxy_request_log=persist_proxy_request_log,
            log_rag_error_private=_log_rag_error_private,
            _append_trace_warning=_append_trace_warning,
        )
    except Exception as e:
        if not private_build:
            w.log_webui_error("rag_routes.chat_completions", e, {"stage": "prepare_rag"})
        _log_rag_error_private("prepare_rag", e, private_build=private_build)
        return jsonify({"error": str(e)}), 500

    if prepared.early_return is not None:
        return prepared.early_return
    ollama_messages = prepared.ollama_messages
    use_model = prepared.use_model
    use_model_ref[0] = use_model
    client_visible_model = prepared.client_visible_model
    ollama_think = prepared.ollama_think
    ollama_messages_have_images = prepared.ollama_messages_have_images

    return dispatch_response(
        w=w,
        trace=trace,
        use_native_tools=use_native_tools,
        tools=tools,
        tool_choice_effective=tool_choice_effective,
        use_model=use_model,
        ollama_messages=ollama_messages,
        ollama_think=ollama_think,
        ollama_messages_have_images=ollama_messages_have_images,
        input_budget=input_budget,
        trace_id=trace_id,
        proxy_db_path=proxy_db_path,
        has_tool_result=has_tool_result,
        tool_result_indicates_failure=tool_result_indicates_failure,
        tool_loop_stats=tool_loop_stats,
        stream=stream,
        build_sse_streaming=build_sse_streaming,
        private_build=private_build,
        client_visible_model=client_visible_model,
        chat_client=chat_client,
        include_reasoning_content=include_reasoning_content,
        include_rag_metadata=include_rag_metadata,
        user_query=user_query,
        log_preview=log_preview,
        start_time=start_time,
        rag_ctx=rag_ctx,
        rag_ctx_for_log=rag_ctx_for_log,
        rag_timings=rag_timings,
        requested_model=requested_model,
        is_autocomplete=is_autocomplete,
        post_tool_success_turn=post_tool_success_turn,
        selected_edit_tool_name=selected_edit_tool_name,
        selected_edit_tool=selected_edit_tool,
        selected_tool_write_capable=selected_tool_write_capable,
        last_user=last_user,
        ollama_options_overlay=ollama_options_overlay,
        publish_trace=publish_trace,
        publish_response_artifacts=publish_response_artifacts,
        persist_proxy_request_log=persist_proxy_request_log,
        log_rag_error_private=_log_rag_error_private,
        rag_request_completed_payload=_rag_request_completed_payload,
    )
