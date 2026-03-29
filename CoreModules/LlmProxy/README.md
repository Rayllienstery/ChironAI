# LlmProxy (Core Module)

Installable package **`llm-proxy`**: OpenAI-compatible HTTP surface for the ChironAI RAG proxy—**Flask blueprint** registering:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1` | API metadata |
| GET | `/v1/models` | Lists logical model ids: RAG chat (`ChironAI-Worker` by default) and, when configured, autocomplete (`ChironAI-Autocomplete` by default) |
| POST | `/v1/chat/completions` | Chat with optional RAG, tools, streaming |
| POST | `/v1/files/apply-edit` | Apply a line/column range edit in the workspace |
| POST | `/v1/external-docs/ingest` | Ingest an external-docs source (host-dependent) |

Implementation lives inside `llm_proxy/`; **host-specific** services (settings DB, RAG use cases, Ollama client, prompts) are injected via **`LlmProxyWiring`**—see [`api/http/llm_proxy_wiring.py`](../../api/http/llm_proxy_wiring.py) in the main repo.

## Installation

From the repository root:

```bash
pip install -e CoreModules/LlmProxy
```

Pytest adds `CoreModules/LlmProxy` to `pythonpath` in the root [`pyproject.toml`](../../pyproject.toml).

## Public API

- **`create_v1_blueprint(wiring: LlmProxyWiring) -> flask.Blueprint`** — register on the Flask app with `url_prefix=""` so paths stay `/v1/...`.
- **`LlmProxyWiring`** — frozen dataclass of callables and config (`contracts.py`).
- **`LlmProxyRuntimeConfig`** — module-owned defaults (logical model id, TTLs for edit retry caches); override via environment:

| Variable | Purpose |
|----------|---------|
| `LLM_PROXY_RAG_MODEL_ID` | Logical model id for RAG chat in `/v1/models` (default `ChironAI-Worker`; legacy alias `rag-ollama` still accepted in requests) |
| `LLM_PROXY_AUTOCOMPLETE_MODEL_ID` | Logical id for fast inline completion (default `ChironAI-Autocomplete`) |
| `LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL` | Concrete Ollama tag for autocomplete (overrides WebUI `proxy_autocomplete_model` when set) |
| `LLM_PROXY_AUTOCOMPLETE_SYSTEM_PREFIX` / `LLM_PROXY_AUTOCOMPLETE_SYSTEM_SUFFIX` | Optional overrides for minimal system prompt when using the autocomplete logical id |
| `LLM_PROXY_RECENT_SUCCESS_TTL_S` | TTL for cross-request “success” suppression (default `45`) |
| `LLM_PROXY_RECENT_NOOP_TTL_S` | TTL for noop retry tracking (default `120`) |

Autocomplete is **additive**: same `/v1/chat/completions` endpoint; requests with `model` set to the autocomplete logical id skip RAG and use a small Ollama model from WebUI or env. The second entry appears in `/v1/models` only after that backend model is configured.

## Wiring contract

The host must supply:

- **Workspace**: `workspace_root: Callable[[], Path]` — repository root for path resolution and apply-edit.
- **RAG**: `get_rag_answer_params`, `build_rag_context`, `prepare_ollama_messages`, factories for `RagContext` / `RagQuestionRequest`, prompt resolution (`get_rag_prompt_prefix_suffix`, `rag_prompt_file_exists`).
- **Observability**: proxy status + trace hooks (`set_proxy_status`, `set_current_trace`, …), `log_webui_error`, optional session/logs for request history.
- **Autocomplete**: `get_autocomplete_ollama_model` on `LlmProxyWiring` — returns the resolved Ollama tag for the autocomplete logical id (or `None` if unset); used to list `/v1/models` and route completions without RAG.
- **External docs (optional)**: `LlmProxyExternalDocsBundle` with merged RAG / GitHub ingest callables; if `available` is false, merged retrieval is skipped.
- **Web supplement (optional)**: `build_web_supplement_for_proxy` on `LlmProxyWiring`—free DuckDuckGo snippets from [`CoreModules/WebInteraction`](../WebInteraction/README.md), gated by saved WebUI settings and env (`WEB_INTERACTION_ENABLED`, `WEB_INTERACTION_MAX_RESULTS`). Injected via `prepare_ollama_messages(..., web_supplement=...)`.
- **Ingest endpoint**: `ingest_external_source(source_id) -> (dict, http_status)` or `None` to return 503.

ChironAI’s [`rag_routes`](../../api/http/rag_routes.py) re-exports several application symbols so tests can `monkeypatch` them before `create_app()`.

## Tool calling (IDE clients)

When the request includes a non-empty `tools` list and `tool_choice` is not `"none"`, the proxy acts as a **mediator only**: it injects RAG and prompt template via `prepare_ollama_messages(..., native_tools=True)`, forwards `tools` and messages to **Ollama `/api/chat` native tool calling**, and maps the response back to OpenAI-style `tool_calls` (including streaming: one aggregated completion is emitted as SSE). The model must support tools; use a current Ollama build with tool calling enabled.

If `tool_choice` is `"none"` or `tools` is empty, the legacy text-only path (no synthetic JSON tool shim) is used as before.

## Pipeline behavior (WebUI + env)

The WebUI **LLM Proxy → Model Settings** block **Proxy pipeline** persists three flags in `proxy_settings` (defaults match **Legacy**, so upgrades stay behavior-preserving). Each request’s effective values are also attached to the proxy trace under `request.proxy_pipeline_policy`.

| Setting (`proxy_settings` key) | Legacy default | What it controls |
|--------------------------------|----------------|------------------|
| `proxy_tool_policy` | `normalize` | **`passthrough`**: skip rewriting native `tool_calls` arguments after Ollama (`_normalize_native_openai_tool_calls_for_edit_tools`) and skip the extra multi-file append system hint. **`normalize`**: current path rewrite + hint behavior. |
| `proxy_stateful_guards` | `true` | **`false`**: no cross-request `edit_state` updates for success/noop, no `noop_retry_blocked` early response, no transcript heuristics that force `post_tool_success_turn` (trailing noop, duplicate user), no Swift `tool_choice` `none`→`auto` override, and no `_POST_TOOL_SUCCESS_SYSTEM` injection on the text-tool path. |
| `proxy_text_tool_retries` | `true` | **`false`**: no strict JSON retries, no `_maybe_retry_edit_payload_full_file`, and no minimal empty-response chat for the stream tool path—only the primary model output is used (plus the existing compact retry on Ollama errors where applicable). |

Environment variables **override** saved settings for automation/CI (non-empty / recognized values only):

| Variable | Values |
|----------|--------|
| `LLM_PROXY_TOOL_POLICY` | `normalize` or `passthrough` |
| `LLM_PROXY_STATEFUL_GUARDS` | `0`/`false`/`off` or `1`/`true`/`on` |
| `LLM_PROXY_TEXT_TOOL_RETRIES` | same as above |

**Strict pass-through** (as in the product plan) is: `proxy_tool_policy=passthrough`, `proxy_stateful_guards=false`, `proxy_text_tool_retries=false`. RAG/system assembly from the template remains the proxy’s intentional enrichment; these flags only gate “extra” mutation and hidden follow-up chats.

## Dependencies

- Python ≥ 3.10
- **Flask** ≥ 2.3

No dependency on ChironAI `domain` / `application` inside the package; those are wired from the host.

## Version

See [`pyproject.toml`](pyproject.toml) (`version`).
