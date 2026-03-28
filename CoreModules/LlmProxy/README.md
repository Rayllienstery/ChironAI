# LlmProxy (Core Module)

Installable package **`llm-proxy`**: OpenAI-compatible HTTP surface for the ChironAI RAG proxy—**Flask blueprint** registering:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1` | API metadata |
| GET | `/v1/models` | Lists the logical RAG model id (default `rag-ollama`) |
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
| `LLM_PROXY_RAG_MODEL_ID` | Logical model id exposed in `/v1/models` (default `rag-ollama`) |
| `LLM_PROXY_RECENT_SUCCESS_TTL_S` | TTL for cross-request “success” suppression (default `45`) |
| `LLM_PROXY_RECENT_NOOP_TTL_S` | TTL for noop retry tracking (default `120`) |

## Wiring contract

The host must supply:

- **Workspace**: `workspace_root: Callable[[], Path]` — repository root for path resolution and apply-edit.
- **RAG**: `get_rag_answer_params`, `build_rag_context`, `prepare_ollama_messages`, factories for `RagContext` / `RagQuestionRequest`, prompt resolution (`get_rag_prompt_prefix_suffix`, `rag_prompt_file_exists`).
- **Observability**: proxy status + trace hooks (`set_proxy_status`, `set_current_trace`, …), `log_webui_error`, optional session/logs for request history.
- **External docs (optional)**: `LlmProxyExternalDocsBundle` with merged RAG / GitHub ingest callables; if `available` is false, merged retrieval is skipped.
- **Ingest endpoint**: `ingest_external_source(source_id) -> (dict, http_status)` or `None` to return 503.

ChironAI’s [`rag_routes`](../../api/http/rag_routes.py) re-exports several application symbols so tests can `monkeypatch` them before `create_app()`.

## Tool calling (IDE clients)

When the request includes a non-empty `tools` list and `tool_choice` is not `"none"`, the proxy acts as a **mediator only**: it injects RAG and prompt template via `prepare_ollama_messages(..., native_tools=True)`, forwards `tools` and messages to **Ollama `/api/chat` native tool calling**, and maps the response back to OpenAI-style `tool_calls` (including streaming: one aggregated completion is emitted as SSE). The model must support tools; use a current Ollama build with tool calling enabled.

If `tool_choice` is `"none"` or `tools` is empty, the legacy text-only path (no synthetic JSON tool shim) is used as before.

## Dependencies

- Python ≥ 3.10
- **Flask** ≥ 2.3

No dependency on ChironAI `domain` / `application` inside the package; those are wired from the host.

## Version

See [`pyproject.toml`](pyproject.toml) (`version`).
