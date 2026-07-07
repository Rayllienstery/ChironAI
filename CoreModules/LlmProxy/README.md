# LlmProxy (Core Module)

Installable package **`llm-proxy`**: **OpenAI-** and **Anthropic Messages–** compatible HTTP surface for the ChironAI RAG proxy—**Flask blueprint** registering:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1` | API metadata |
| GET | `/v1/models` | **OpenAI clients:** `object`/`data` list of **build ids** plus optional **ChironAI-Autocomplete** when configured. Each OpenAI-shaped row includes Chiron extension **`supports_vision`: always `true`**, Kilo/Roo/Cline aliases such as **`supportsImages: true`**, and OpenCode/models.dev-style **`attachment: true`** plus **`modalities.input: ["text", "image"]`** so clients do not hide or strip image attachment; if an Ollama-backed build resolves to a text-only upstream tag, image turns can be routed to a vision fallback. **Anthropic clients:** send header `anthropic-version` (any non-empty value, e.g. `2023-06-01`) for Anthropic-shaped `data` / `first_id` / `has_more`. |
| GET | `/v1/models/<id>` | Returns one OpenAI-shaped model row with the same vision/tool aliases. If a client probes a manually configured concrete Ollama tag instead of a build id, the proxy returns a synthetic local row so the client still sends image attachments. |
| POST | `/v1/messages` | **Anthropic Messages API** — translated to the same pipeline as `POST /v1/chat/completions` (RAG, tools, streaming). |
| POST | `/v1/responses` | **OpenAI Responses API** — normalized to provider-backed chat. |
| POST | `/v1/chat/completions` | Chat with optional RAG, tools, streaming |
| POST | `/v1/files/apply-edit` | Apply a line/column range edit in the workspace |
| POST | `/v1/external-docs/ingest` | Ingest an external-docs source (host-dependent) |

**Build presets:** user-defined entries in app_settings (`llm_proxy_builds`) appear in **GET `/v1/models`** on the main server port. Use each build's `id` as `model` in **POST `/v1/chat/completions`**. Optional **ChironAI-Autocomplete** in `/v1/models` is controlled by `llm_proxy.v1_include_autocomplete_logical_model` (default true) or env `LLM_PROXY_V1_INCLUDE_AUTOCOMPLETE_MODEL=0`.

Implementation lives inside `llm_proxy/`; **host-specific** services (settings DB, RAG use cases, provider runtime, prompts) are injected via **`LlmProxyWiring`**—see [`api/http/llm_proxy_wiring.py`](../../api/http/llm_proxy_wiring.py) in the main repo.

## Chat Pipeline

Use **`POST /v1/chat/completions`** (or **`POST /v1/messages`** / **`POST /v1/responses`** for compatibility clients) when you want the full product behavior:

- **LLM Proxy builds** from app settings (`llm_proxy_builds`) resolve through the provider runtime.
- **SQLite proxy history** (WebUI **Proxy Logs**, `session_id=proxy`) for completed requests, plus RAG timing metadata where applicable (`GET /api/webui/proxy-logs`).

Raw Ollama-compatible `/api/tags`, `/api/show`, `/api/generate`, `/api/chat`,
and legacy `/v1/completions` are no longer registered by the core proxy.
Ollama-native behavior belongs in `chironai-extension-ollama-provider`
(`extensions/bundled/ollama-provider` is the trusted bootstrap/offline mirror).

### Vision (multimodal images) on `POST /v1/chat/completions` and `POST /v1/responses`

OpenAI-style user messages may use multipart `content`: an array of `{ "type": "text", "text": "..." }` and `{ "type": "image_url", "image_url": { "url": "..." } }`. AI SDK/OpenCode-style image parts such as `{ "type": "file", "mediaType": "image/png", "data": "..." }` and `{ "type": "image", "mediaType": "image/png", "image": "..." }` are normalized to the same image path.

**Client routing:** Kilo Code and other `openai-compatible` clients typically call **`POST /v1/chat/completions`**. OpenCode and other Responses API clients call **`POST /v1/responses`** with `input` items such as `{ "type": "input_text", "text": "..." }` and `{ "type": "input_image", "image_url": "data:image/...;base64,..." }` (or a nested `{ "url": "..." }` object). The proxy maps those `input_image` parts to the same OpenAI multipart `image_url` path before forwarding to Ollama.

- **Supported toward Ollama:** `image_url.url` values that are **`data:image/...;base64,...`** data URLs. The proxy validates and forwards them as Ollama’s native **`images`** array on the same user message (base64 payload after `base64,`), with adjacent text in **`content`**.
- **Inline paste in text (user turns):** before sanitisation, the proxy **promotes** any valid `data:image/...;base64,...` substring inside user string `content` or inside user `type: "text"` parts into proper `image_url` parts so they survive the pipeline and populate Ollama `images` (see `promote_inline_data_image_urls_in_content` in [`rag_service.infrastructure.openai_multipart_vision`](../RagService/rag_service/infrastructure/openai_multipart_vision.py)).
- **Not loaded by the proxy (default):** plain **`http://` / `https://`** image URLs are replaced with a short in-band note (no server-side fetch; avoids SSRF). Use a data URL or host a client/provider surface that inlines the image as base64.
  - **Optional (unsafe-by-default):** set `LLM_PROXY_VISION_FETCH_EXTERNAL_URLS=1` to enable **server-side fetching** of `http(s)` image URLs and conversion to `data:image/...;base64,...` (guarded with best-effort SSRF checks + size limits).
- **Limits:** decoded size per image, max images per message, and a text length cap are defined in [`rag_service.infrastructure.openai_multipart_vision`](../RagService/rag_service/infrastructure/openai_multipart_vision.py).

Proxy traces expose **`images_count`** per Ollama message when `images` is present; base64 blobs are not expanded into trace previews.

- **`tool_choice`:** OpenAI allows object values (e.g. `{"type":"auto"}`). Ollama’s native **`/api/chat`** expects a small string or the field omitted; the proxy maps unsupported shapes to **omit** the field (default auto) and maps string **`none`** / dict **`{"type":"none"}`** to disabling tools for routing.
- **Tools + vision:** when a request includes images, the proxy suppresses native tool forwarding for that turn before calling Ollama. This avoids adapter-level 400 responses from models that support tools and vision separately but not together.
- **Text-only Ollama tags:** the proxy reads Ollama `/api/tags` capabilities. If the selected build model lacks `vision`, it routes the image turn to a vision-capable fallback, preferring the build's optional `vision_model`, then `LLM_PROXY_VISION_FALLBACK_MODEL`, then known local/cloud vision tags.

#### Troubleshooting: `ERROR: Cannot read "image.png" (this model does not support image input)`

If you see that string inside the **user message** (as opposed to an HTTP error response), it means the **client** failed to attach/read the local image before sending the request. The proxy cannot read `image.png` from the user’s machine via a file path in text. To send an image through `POST /v1/chat/completions` or `POST /v1/responses`, the client must include a `data:image/...;base64,...` data URL (as `image_url` in chat/completions or `input_image.image_url` in responses).

#### Responses API `input_image` with `file_id`

Some Responses API clients send `{ "type": "input_image", "file_id": "..." }` after uploading files to OpenAI storage. ChironAI does **not** resolve OpenAI `file_id` references. Those parts are replaced with:

`[Image omitted: Responses file_id references are not resolved by the proxy.]`

**Workaround:** configure the client to inline images as `image_url` (including `data:image/...;base64,...`) or use `POST /v1/chat/completions` with OpenAI-style `image_url` content parts.

**OpenCode (`@ai-sdk/openai-compatible`):** custom models default to text-only unless you declare `modalities` in `~/.config/opencode/opencode.jsonc`. Without `"input": ["text", "image"]`, OpenCode strips attachments client-side before the proxy sees them. Regenerate a working config from current WebUI builds + proxy key:

```bash
python scripts/configure_opencode_chiron_vision.py
```

Defaults: `WEBUI_DB_PATH` or `<repo>/logs/webui.db` → `~/.config/opencode/opencode.jsonc`. Use `--db-path`, `--output`, and `--base-url` to override.

Then restart OpenCode and pick a build id (e.g. `Hard-worker`) under the `chiron` provider.

#### Vision flags

- `LLM_PROXY_VISION_FETCH_EXTERNAL_URLS` (default `0`): when enabled, the proxy may fetch `http(s)` `image_url.url` server-side and inline it as a `data:image/...;base64,...` URL. This is guarded with best-effort SSRF checks and strict size limits, but should be enabled only in trusted environments.
- `LLM_PROXY_VISION_FALLBACK_MODEL` (default empty): preferred Ollama model tag for image turns when the selected build model is present in `/api/tags` but lacks `vision`.
- `LLM_PROXY_VISION_READ_LOCAL_FILES` (default `0`): when enabled, the proxy attempts to detect image file path hints in **user** string `content` or the **first** user `type: "text"` part that contains a hint, and, if the file exists on the proxy host, inlines it as an OpenAI multipart `image_url` data URL. This is primarily a Copilot/Kilo workaround for prompts that include `ERROR: Cannot read "image.png" ...`.
- `LLM_PROXY_VISION_ALLOW_ABS_PATHS` (default `0`): when `LLM_PROXY_VISION_READ_LOCAL_FILES=1`, controls whether absolute paths are allowed. Default is workspace-only.

## Chiron proxy API key

All Chiron `/v1*` endpoints are fail-closed and require a WebUI-managed API key:

- Generate or reveal the key in WebUI: **RAG Fusion Proxy** -> **Overview** -> **Security**. Use **Generate key** for the first key, **Reveal key** to copy the current key, and **Regenerate key** to rotate it.
- The key is stored in `app_settings` under `llm_proxy_api_key` as a recoverable admin secret plus `sha256`, `prefix`, `created_at`, and `rotated_at`. Runtime auth verifies via the hash; WebUI can reveal the key again for IDE/OpenWebUI setup.
- Send the key as either `Authorization: Bearer <key>` or `x-api-key: <key>`.
- If no key is configured, `/v1*` returns `503` with `server_configuration_error`; if the request key is missing or wrong, it returns `401` with `authentication_error`.
- Regenerating rotates the single active key and immediately invalidates the old one. Deleting the key closes `/v1*` again until a new key is generated.
- Raw Ollama-compatible routes are not exposed by this core proxy. Use the `ollama-provider` extension for Ollama-native management and compatibility behavior.

OpenWebUI has its own account/API-key protection. That protects OpenWebUI itself, but it does not protect this Chiron proxy if clients can reach `http://host:port/v1/...` directly. When configuring OpenWebUI as an OpenAI-compatible `/v1` client for Chiron, set the Chiron proxy key as the provider API key/Bearer token.

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

Autocomplete is **additive**: same `/v1/chat/completions` endpoint; requests with `model` set to the autocomplete logical id skip RAG (and web supplement) and use the small Ollama model from WebUI or env. System prompt comes from the same WebUI **Prompt template** (`prompt_name`) as chat. The second entry appears in `/v1/models` only after that backend model is configured.

### Anthropic Messages clients (base URL)

Point any Anthropic Messages–compatible client at this host (same port as the main Flask app), e.g.:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8080
export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_API_KEY=""
```

Use a **build id** from `GET /v1/models` (with header `anthropic-version`, e.g. `2023-06-01`) or a concrete Ollama tag as the request `model`. Streaming uses Anthropic SSE synthesized from the internal OpenAI-shaped stream.

**Known limitations:** exotic Anthropic content blocks (images, PDFs, etc.) may not round-trip; agent-style **text** and **tool_use** / **tool_result** are supported. See `llm_proxy/anthropic_compat.py`.

## Wiring contract

The host must supply:

- **Workspace**: `workspace_root: Callable[[], Path]` — repository root for path resolution and apply-edit.
- **RAG**: `get_rag_answer_params`, `build_rag_context`, `prepare_ollama_messages`, factories for `RagContext` / `RagQuestionRequest`, prompt resolution (`get_rag_prompt_prefix_suffix`, `rag_prompt_file_exists`).
- **Observability**: proxy status + trace hooks (`set_proxy_status`, `set_current_trace`, …), `log_webui_error`, optional session/logs for request history.
- **Provider runtime**: `llm_runtime` / `provider_registry` resolve model calls through extension-owned providers.
- **Autocomplete**: `get_autocomplete_ollama_model` on `LlmProxyWiring` — legacy name for the resolved provider model behind the autocomplete logical id (or `None` if unset); used to list `/v1/models`.
- **External docs (optional)**: `LlmProxyExternalDocsBundle` with merged RAG / GitHub ingest callables; if `available` is false, merged retrieval is skipped.
- **Web supplement (optional)**: `build_web_supplement_for_proxy` on `LlmProxyWiring`—free DuckDuckGo snippets from [`CoreModules/WebInteraction`](../WebInteraction/README.md), gated by saved WebUI settings and env (`WEB_INTERACTION_ENABLED`, `WEB_INTERACTION_MAX_RESULTS`). Injected via `prepare_ollama_messages(..., web_supplement=...)`.
- **Ingest endpoint**: `ingest_external_source(source_id) -> (dict, http_status)` or `None` to return 503.

ChironAI’s [`rag_routes`](../../api/http/rag_routes.py) re-exports several application symbols so tests can `monkeypatch` them before `create_app()`.

## Tool calling (IDE clients)

When the request includes a non-empty `tools` list and `tool_choice` is not `"none"`, the proxy acts as a **mediator only**: it injects RAG and prompt template via `prepare_ollama_messages(..., native_tools=True)`, forwards `tools` and messages through the provider runtime, and maps the response back to OpenAI-style `tool_calls`. If the client requests `stream: true`, the proxy still returns SSE by synthesizing chunks from the provider result when needed. The selected model must support tools.

Plain chat (no native tools) likewise goes through the provider runtime; OpenAI streaming responses are synthesized from provider stream events.

### Wire-format compatibility modules

- `llm_proxy/ollama_compat.py` — intentional re-export boundary for OpenAI-shaped chat/tool/vision normalization (not provider HTTP ownership).
- `llm_proxy/chat_completions_legacy_tool_stream.py` — buffered SSE path for older IDE clients that stream with `tools` before native tool streaming.

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
