# LlmProxy (Core Module)

Installable package **`llm-proxy`**: **OpenAI-** and **Anthropic Messages–** compatible HTTP surface for the ChironAI RAG proxy—**Flask blueprint** registering:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1` | API metadata |
| GET | `/v1/models` | **OpenAI clients:** `object`/`data` list of **build ids** plus optional **ChironAI-Autocomplete** when configured. **Anthropic clients:** send header `anthropic-version` (any non-empty value, e.g. `2023-06-01`) for Anthropic-shaped `data` / `first_id` / `has_more`. |
| POST | `/v1/messages` | **Anthropic Messages API** — translated to the same pipeline as `POST /v1/chat/completions` (RAG, tools, streaming). Empty `x-api-key` is accepted for local use (e.g. Claude Code + Ollama-style env). |
| POST | `/v1/chat/completions` | Chat with optional RAG, tools, streaming |
| POST | `/v1/completions` | OpenAI legacy completions (`choices[].text`) — implemented as transparent **`POST …/api/generate`** upstream (same as raw Ollama). No RAG, no WebUI prompt template, no web supplement. Optional `LLM_PROXY_COMPLETIONS_RAW` (`true` by default: sets Ollama `raw`). Zed **edit prediction** (`open_ai_compatible_api`): use `http://<host>:<port>/v1/completions`. |
| POST | `/v1/files/apply-edit` | Apply a line/column range edit in the workspace |
| POST | `/v1/external-docs/ingest` | Ingest an external-docs source (host-dependent) |
| GET | `/api/tags` | Transparent proxy to upstream Ollama (model list) |
| POST | `/api/show` | Transparent proxy to upstream Ollama (model details) |
| POST | `/api/generate` | Transparent proxy to upstream Ollama `/api/generate` |
| POST | `/api/chat` | Transparent proxy to upstream Ollama `/api/chat` |

**Build presets:** user-defined entries in app_settings (`llm_proxy_builds`) appear in **GET `/v1/models`** on the main server port and on the optional **build proxy** port (default **8087**, `config/server.yaml` → `build_proxy`). Use each build’s `id` as `model` in **POST `/v1/chat/completions`** (`dumb` = RAG + Ollama pipeline per `application/llm_proxy_builds.py`). You may also pass a **concrete Ollama tag** as `model` for passthrough chat. Optional **ChironAI-Autocomplete** in `/v1/models` is controlled by `llm_proxy.v1_include_autocomplete_logical_model` (default true) or env `LLM_PROXY_V1_INCLUDE_AUTOCOMPLETE_MODEL=0`.

Implementation lives inside `llm_proxy/`; **host-specific** services (settings DB, RAG use cases, Ollama client, prompts) are injected via **`LlmProxyWiring`**—see [`api/http/llm_proxy_wiring.py`](../../api/http/llm_proxy_wiring.py) in the main repo.

## Chat pipeline vs raw Ollama (`/v1/...` vs `/api/...`)

Use **`POST /v1/chat/completions`** (or **`POST /v1/messages`** for Anthropic-shaped clients) when you want the full product behavior:

- **LLM Proxy builds** from app settings (`llm_proxy_builds`): `dumb` (RAG + Ollama chat), or a **concrete Ollama model id** for the same RAG/template path as a plain tag.
- **SQLite proxy history** (WebUI **Proxy Logs**, `session_id=proxy`) for completed requests, plus RAG timing metadata where applicable (`GET /api/webui/proxy-logs`).

The **`/api/tags`**, **`/api/show`**, **`/api/generate`**, and **`/api/chat`** routes exist so clients can point at this host as an **Ollama base URL** (e.g. Zed). They **forward the JSON body to upstream Ollama** and do **not** apply RAG, WebUI prompt templates, build presets, or the same **proxy** logging as `/v1/chat/completions`. Prefer **`/v1/chat/completions`** for observability and RAG unless you intentionally want raw Ollama.

### Vision (multimodal images) on `POST /v1/chat/completions`

OpenAI-style user messages may use multipart `content`: an array of `{ "type": "text", "text": "..." }` and `{ "type": "image_url", "image_url": { "url": "..." } }`.

- **Supported toward Ollama:** `image_url.url` values that are **`data:image/...;base64,...`** data URLs. The proxy validates and forwards them as Ollama’s native **`images`** array on the same user message (base64 payload after `base64,`), with adjacent text in **`content`**.
- **Not loaded by the proxy:** plain **`http://` / `https://`** image URLs are replaced with a short in-band note (no server-side fetch; avoids SSRF). Use a data URL, call upstream **`POST /api/chat`** directly, or host a client that inlines the image as base64.
- **Limits:** decoded size per image, max images per message, and the usual text sanitiser for huge inline base64 pasted into **string-only** `content` are defined in [`infrastructure/ollama/openai_multipart_vision.py`](../../infrastructure/ollama/openai_multipart_vision.py).

Proxy traces expose **`images_count`** per Ollama message when `images` is present; base64 blobs are not expanded into trace previews.

- **`tool_choice`:** OpenAI allows object values (e.g. `{"type":"auto"}`). Ollama’s native **`/api/chat`** expects a small string or the field omitted; the proxy maps unsupported shapes to **omit** the field (default auto) and maps string **`none`** / dict **`{"type":"none"}`** to disabling tools for routing.
- **Tools + vision:** when **`tools`** is sent to Ollama, the proxy **drops `images`** from outbound messages for that request only (trace still reflects the pre-strip list). Some backends (including several cloud models) return **400** if `images` and `tools` are combined.

**`POST /v1/completions`** is a separate legacy shape (OpenAI `prompt` / `input` → Ollama **`/api/generate`**); it is not merged into the same analytics semantics as chat completions.

**Network note:** the server often binds `0.0.0.0` ([`config/server.yaml`](../../config/server.yaml)); there is **no API key** on the proxy by default—use only on a trusted network.

## Installation

From the repository root:

```bash
pip install -e CoreModules/LlmProxy
```

Pytest adds `CoreModules/LlmProxy` to `pythonpath` in the root [`pyproject.toml`](../../pyproject.toml).

## Public API

- **`create_v1_blueprint(wiring: LlmProxyWiring) -> flask.Blueprint`** — register on the Flask app with `url_prefix=""` so paths stay `/v1/...`.
- **`LlmProxyWiring`** — frozen dataclass of callables and config (`contracts.py`).
- **`LlmProxyRuntimeConfig`** — module-owned defaults (autocomplete logical id); override via environment:

| Variable | Purpose |
|----------|---------|
| `LLM_PROXY_AUTOCOMPLETE_MODEL_ID` | Logical id for fast inline completion (default `ChironAI-Autocomplete`) |
| `LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL` | Concrete Ollama tag for autocomplete (overrides WebUI `proxy_autocomplete_model` when set) |
| `LLM_PROXY_COMPLETIONS_RAW` | If not `0`/`false`/`no`, `/v1/completions` sets Ollama `raw: true` on `/api/generate` (default: on) |

Autocomplete is **additive**: same `/v1/chat/completions` endpoint; requests with `model` set to the autocomplete logical id skip RAG (and web supplement) and use the small Ollama model from WebUI or env. System prompt comes from the same WebUI **Prompt template** (`prompt_name`) as chat. The second entry appears in `/v1/models` only after that backend model is configured.

### Claude Code (Anthropic base URL)

Point Claude Code at this host (same port as the main Flask app), e.g.:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8080
export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_API_KEY=""
claude --model your-build-id
```

Use a **build id** from `GET /v1/models` or a concrete Ollama tag as `--model`. Streaming uses Anthropic SSE synthesized from the internal OpenAI-shaped stream.

**Known limitations:** exotic Anthropic content blocks (images, PDFs, etc.) may not round-trip; agent-style **text** and **tool_use** / **tool_result** are supported. See `llm_proxy/anthropic_compat.py`.

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

When the request includes a non-empty `tools` list and `tool_choice` is not `"none"`, the proxy acts as a **mediator only**: it injects RAG and prompt template via `prepare_ollama_messages(..., native_tools=True)`, forwards `tools` and messages to **Ollama `/api/chat` native tool calling** with `stream: false`, and maps the response back to OpenAI-style `tool_calls`. If the client requests `stream: true`, the proxy still returns SSE by **synthesizing** chunks from that single Ollama reply (Ollama is not called with streaming on this path). The model must support tools; use a current Ollama build with tool calling enabled.

Plain chat (no native tools) likewise uses **non-streaming** `/api/chat`; OpenAI streaming responses are synthesized the same way. Legacy `/v1/completions` always uses **`stream: false`** toward Ollama `/api/generate`; optional client streaming is synthesized from the full generate response.

If `tool_choice` is `"none"` or `tools` is empty, the legacy text-only path (no synthetic JSON tool shim) is used as before.

## Proxy pipeline (single mode)

The handler runs in **passthrough-only** mode. The proxy still enriches requests the same way as before for RAG, prompt templates, optional web/external-docs context, and OpenAI↔Ollama mapping.

It **does not**:

- Rewrite native `tool_calls` arguments returned by Ollama (client sees the model’s JSON as mapped by the bridge).
- Inject extra system hints aimed at multi-file append workflows.
- Keep cross-request edit success / noop state, block “repeated noop” loops early, extend `post_tool_success_turn` with transcript heuristics, override `tool_choice: none` to `auto` for Swift-style edit prompts, or inject post-tool success system text on the legacy JSON-tool path.
- Run hidden follow-up model calls for strict JSON tool retries, full-file edit retries, or minimal empty-response recovery on the stream tool path (the compact Ollama error retry when the primary chat call fails may still apply).

The proxy trace includes `request.proxy_pipeline: "passthrough_only"` for visibility.

**Breaking change:** `proxy_tool_policy`, `proxy_stateful_guards`, `proxy_text_tool_retries`, and env vars `LLM_PROXY_TOOL_POLICY`, `LLM_PROXY_STATEFUL_GUARDS`, `LLM_PROXY_TEXT_TOOL_RETRIES`, `LLM_PROXY_RECENT_SUCCESS_TTL_S`, `LLM_PROXY_RECENT_NOOP_TTL_S` are removed. Older `proxy_settings` JSON keys in the DB are ignored.

## Dependencies

- Python ≥ 3.10
- **Flask** ≥ 2.3

No dependency on ChironAI `domain` / `application` inside the package; those are wired from the host.

## Version

See [`pyproject.toml`](pyproject.toml) (`version`).
