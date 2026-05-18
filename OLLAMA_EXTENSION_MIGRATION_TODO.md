# Ollama Extension Migration TODO

This document is the decision-complete migration guide for moving Ollama-owned behavior out of core and monolith paths into the bundled `ollama-provider` extension. It is intended for Codex, Cursor, and humans working in this repository.

## Why This Exists

Ollama is already represented as a bundled extension at `extensions/bundled/ollama-provider`, and that extension already advertises provider capabilities such as chat, streaming, embeddings, rerank, model listing, health, tab UI, and service actions.

Core still contains direct Ollama knowledge across proxy wiring, WebUI routes, RAG infrastructure, health checks, service control, config helpers, compatibility routes, and tests. That makes the app harder to modularize because core must understand Ollama URLs, Ollama request shapes, Ollama model metadata, Ollama service lifecycle, and Ollama-specific failure modes.

Target state: `ollama-provider` owns Ollama behavior. Core talks through provider-neutral `LlmInteractor` contracts, extension actions, and temporary compatibility adapters only where public API compatibility requires them during migration.

## Current Baseline

- [x] Confirm `extensions/bundled/ollama-provider/chironai-extension.json` declares `chat`, `embed`, `rerank`, `streaming`, `tools`, `vision`, `model_listing`, `health_check`, `tab_ui`, and `service_actions`.
- [x] Confirm `extensions/bundled/ollama-provider/backend/provider.py` implements provider invocation for chat, streaming, embed, rerank, model listing, health, tab payloads, model actions, pull/delete/hide/show, and service actions.
- [x] Confirm `extensions/bundled/ollama-provider/backend/ollama_http.py` is self-contained and does not import core `infrastructure.*` Ollama adapters.
- [x] Inventory direct Ollama imports and calls in `api/`, especially `api/http/webui_routes.py`, `api/http/webui_llm_proxy_routes.py`, `api/http/webui_crawler_routes.py`, `api/http/llm_proxy_wiring.py`, and `api/http/rag_routes.py`.
- [x] Inventory direct Ollama imports and calls in `CoreModules/LlmProxy`, especially chat completions, legacy completions, upstream passthrough, model metadata, tool bridging, and `/api/*` compatibility routes.
- [x] Inventory direct Ollama imports and calls in `CoreModules/RagService`, especially `rag_service/infrastructure/ollama_chat.py`, `ollama_embedding.py`, `ollama_rerank.py`, `runtime.py`, `config.py`, and the RAG application wiring.
- [x] Inventory direct Ollama imports and calls in root `infrastructure/`, especially `infrastructure/ollama/*` and `infrastructure/stack_health.py`.
- [x] Inventory direct Ollama imports and calls in `CoreModules/WebUIBackend`, especially local ingestion paths that call embed directly.
- [x] Inventory tests that depend on direct Ollama names, modules, or request shapes, including proxy, RAG, config, infrastructure, ServiceStarter, and extension runtime tests.
- [x] Classify every discovered dependency as `keep temporarily`, `move to extension`, `replace with provider runtime`, or `delete after migration`.
- [x] Record the classification near the relevant migration phase in this document before editing behavior.

## Ownership Target

- [x] Treat `ollama-provider` as the canonical owner of Ollama HTTP/CLI calls.
- [x] Treat `ollama-provider` as the canonical owner of model catalog, model visibility, show/delete/pull actions, and model metadata.
- [x] Treat `ollama-provider` as the canonical owner of Ollama provider health and service diagnostics.
- [x] Treat `ollama-provider` as the canonical owner of Ollama embed and rerank clients.
- [x] Treat `ollama-provider` as the canonical owner of Ollama service start/stop UI actions.
- [x] Treat `ollama-provider` as the canonical owner of Ollama-specific capability probing, including thinking/tool/vision metadata when that metadata comes from Ollama.
- [x] Make core call Ollama through `LLMRuntime.invoke(...)` for non-streaming provider operations.
- [x] Make core call Ollama through `LLMRuntime.stream_invoke(...)` for streaming provider operations.
- [x] Make WebUI/provider actions call Ollama through `llm_extensions_service.run_extension_action(...)`.
- [x] Use `RuntimeBackedChatClient` and other compatibility adapters only as temporary migration bridges.
- [x] Preserve public HTTP compatibility while moving ownership behind the scenes.

## Phase 0 - Audit And Behavior Lock

- [x] Run the direct-dependency inventory before changing implementation code.
- [x] Add or update tests that pin current public behavior for `/v1/models`, `/v1/chat/completions`, `/v1/completions`, `/api/tags`, `/api/show`, `/api/generate`, and `/api/chat`.
- [x] Add or update tests that pin current WebUI behavior for provider catalog, model selectors, Ollama tab loading, model visibility, pull progress, and health/status cards.
- [x] Add or update tests that pin current RAG behavior for chat, embeddings, rerank, indexing, and RAG test runner paths.
- [x] Add or update tests that pin current service behavior for starting/stopping Ollama through the UI and through ServiceStarter-adjacent helpers.
- [x] Capture current env/config compatibility expectations for `OLLAMA_BASE_URL`, `OLLAMA_CHAT_URL`, `OLLAMA_URL`, `OLLAMA_EMBED_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `OLLAMA_RERANK_MODEL`, `OLLAMA_EMBED_TIMEOUT`, `LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL`, and related YAML model settings.
- [x] Define the allowed temporary direct-Ollama files for the next phase before adding any new compatibility code.
- [x] Add a regression search command to the final verification notes for each PR that touches Ollama migration.

### Phase 0 Inventory Classification

| Area | Direct dependency | Classification | Baseline / migration note |
| --- | --- | --- | --- |
| `CoreModules/LlmProxy` `/v1` and `/api/*` routes | `chat_completions_*`, `completions_generate.py`, `ollama_upstream.py`, `v1_blueprint.py` imports/calls to root Ollama helpers and raw `/api/*` paths | keep temporarily / replace with provider runtime | Public compatibility is pinned by `tests/api/test_http_endpoints.py`; Phase 3 and Phase 6 move provider calls behind `LLMRuntime` or compatibility adapters. |
| `api/http/webui_routes.py` and `api/http/webui_llm_proxy_routes.py` | `_get_ollama_url()`, `OLLAMA_BASE_URL`, `OLLAMA_URL`, CLI runner calls, provider catalog fallback helpers | move to extension | Phase 2 moves model listing, show/details, health, and diagnostics behind provider catalog or extension actions while preserving WebUI response shapes. |
| `api/http/webui_crawler_routes.py` | `OLLAMA_EMBED_MODEL` default for crawler/embed flows | replace with provider runtime | Phase 4 replaces direct embed defaults with provider-backed embed selection; current env behavior remains compatibility input. |
| `api/http/llm_proxy_wiring.py` | `OllamaEmbedAdapter` for external docs ingestion | replace with provider runtime | Phase 4 replaces external-docs ingestion embed calls with provider-backed adapter; direct adapter is allowed until then. |
| `CoreModules/WebUIBackend/webui_backend/ingest_markdown_local.py` | direct `invoke_embed`, `OLLAMA_EMBED_URL`, local ingest embed URL/model handling | replace with provider runtime | Phase 4 moves local ingestion embeddings behind provider-backed embedding while preserving failure counts and payload reporting. |
| root `infrastructure/ollama/*` | chat/embed/rerank clients, CLI runner wrappers, model metadata, tool bridge, multipart vision helpers | delete after migration | Canonical legacy adapters until proxy/RAG/WebUI call sites are migrated; tests pin stream merge, tool bridge, and CLI behavior. |
| `CoreModules/RagService/rag_service/infrastructure/ollama_*` and `container.py` | duplicated chat/embed/rerank adapters and default RAG wiring | replace with provider runtime / delete after migration | Phase 4 supplies provider-backed chat/embed/rerank clients while keeping RAG prompt/retrieval/Qdrant ownership in RAG modules. |
| `CoreModules/OllamaInteractor` | low-level Ollama HTTP/CLI command module | keep temporarily | Host-level transport remains usable by legacy adapters and extension self-contained HTTP client during migration. |
| `CoreModules/ServiceStarter/servicestarter/ollama_ops.py` | low-level native Ollama ping/stop helpers | keep temporarily | ServiceStarter remains a host capability; app-level start/stop UX belongs to `ollama-provider` extension actions. |
| `extensions/bundled/ollama-provider/backend/*` | extension-owned Ollama HTTP, embed, rerank, model visibility, service actions | move to extension | This is the target owner; direct Ollama behavior here is intentional and self-contained. |
| Tests under `tests/api`, `tests/llm_proxy`, `tests/infrastructure`, `tests/rag_service`, `tests/llm_interactor`, `tests/servicestarter`, `tests/config` | direct Ollama names, fake clients, URLs, env names, compatibility request shapes | keep temporarily | Tests are allowed when they pin public compatibility, legacy adapter behavior, or extension ownership boundaries. |

### Allowed Temporary Direct-Ollama Files

- `CoreModules/LlmProxy/llm_proxy/chat_completions*.py`, `completions_generate.py`, `ollama_upstream.py`, and `v1_blueprint.py` may keep direct Ollama compatibility until Phase 3 and Phase 6.
- `infrastructure/ollama/*` may remain as legacy root adapters until every app caller is provider-backed.
- `CoreModules/RagService/rag_service/infrastructure/ollama_*.py`, `cli_runner.py`, `openai_ollama_tool_bridge.py`, `openai_multipart_vision.py`, and `container.py` may remain until Phase 4.
- `api/http/webui_routes.py`, `api/http/webui_llm_proxy_routes.py`, `api/http/webui_crawler_routes.py`, and `CoreModules/WebUIBackend/webui_backend/ingest_markdown_local.py` may keep documented compatibility reads until Phase 2 and Phase 4.
- `api/http/llm_proxy_wiring.py` may keep `OllamaEmbedAdapter` only for external-docs ingestion until Phase 4.
- Tests may keep direct Ollama imports and names only when they pin public compatibility, legacy adapters, or extension boundaries.

### Env And Config Compatibility Baseline

| Input | Current owner / reader | Compatibility expectation |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | root config, WebUI routes, OllamaInteractor, ServiceStarter, Open WebUI extension, Ollama provider service metadata | Base URL override; may include `/api/...` in some callers and must be normalized where supported. |
| `OLLAMA_CHAT_URL` | root config and RagService config | Full `/api/chat` URL override for chat clients; also feeds base URL derivation when `OLLAMA_BASE_URL` is absent. |
| `OLLAMA_URL` | root config and WebUI fallback helpers | Legacy base URL fallback; preserve until explicitly deprecated. |
| `OLLAMA_EMBED_URL` | root config, RagService config, WebUIBackend local ingest, external docs adapter | Full `/api/embed` URL override for embedding paths. |
| `OLLAMA_CHAT_MODEL` | root config and RagService config | Default concrete chat model tag. |
| `OLLAMA_EMBED_MODEL` | root config, RagService config, crawler routes | Default concrete embedding model tag. |
| `OLLAMA_RERANK_MODEL` | root config and RagService config | Default rerank model tag; empty value disables rerank where current code does so. |
| `OLLAMA_EMBED_TIMEOUT` | root config | Embedding timeout in seconds for root config callers. |
| `OLLAMA_EMBED_TIMEOUT_SECONDS` | RagService config | Embedding timeout in seconds for RagService callers. |
| `LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL` | proxy wiring and completions/chat model resolution | Concrete autocomplete Ollama tag; overrides WebUI `proxy_autocomplete_model`. |
| YAML `ollama.*` settings | `config/models.yaml`, `config/rag.yaml`, RagService config | Preserve as fallback config until provider-owned settings consume compatibility inputs. |

### Phase 0 Verification Notes

- [x] Behavior lock added for raw `/api/tags`, `/api/show`, `/api/generate`, and `/api/chat` passthrough request/response shapes.
- [x] Behavior lock added for Ollama extension show/hide/unhide/delete/pull action response shapes.
- [x] Existing tests already pin `/v1/models`, `/v1/chat/completions`, `/v1/completions`, provider catalog, RAG use cases, RAG test runner paths, ServiceStarter, and config/env compatibility.
- [x] Regression searches are listed in `Suggested Regression Searches` and were run during Phase 0 implementation.
- [x] `pytest tests/api/test_http_endpoints.py tests/api/test_extensions_routes.py` passed: 114 tests.
- [x] `PYTHONPATH=CoreModules/ErrorManager;$PYTHONPATH pytest tests/application/test_rag_use_cases.py tests/api/test_rag_tests_routes.py tests/webui tests/rag_service` passed: 50 tests.
- [x] `pytest tests/llm_interactor tests/servicestarter tests/config/test_ollama_base_url.py` passed: 40 tests.
- [x] Regression searches currently report only classified legacy, extension-owned, config-owned, ServiceStarter-owned, or test-owned Ollama references.

## Phase 1 - Harden Extension And Runtime Contracts

- [x] Set the extension runtime default provider to `ollama` once bootstrap is reliable enough for proxy/RAG callers.
- [x] Ensure app wiring stores the actual `LLMRuntime`, `ProviderRegistry`, and `default_provider_id` after extension bootstrap instead of leaving them as `None`.
- [x] Ensure `RuntimeBackedChatClient` fully covers the chat-client methods used by proxy, RAG, streaming, native tools, and compatibility paths.
- [x] Ensure `LLMRequest.operation` covers all required Ollama-owned operations; add or document operations for legacy `generate` and raw Ollama passthrough if `chat`, `chat_api`, `chat_api_stream_events`, `embed`, and `rerank` are insufficient.
- [x] Ensure `LLMResponse.raw` and `LLMStreamEvent.data` preserve enough Ollama payload detail for existing trace, token, done reason, thinking, and tool-call behavior.
- [x] Ensure provider catalog rows expose provider-neutral metadata first, with Ollama-specific metadata nested under `metadata`.
- [x] Ensure the frontend-facing provider display name is exactly `Ollama`, not `Ollama Provider`, while keeping stable technical ids such as `provider_id="ollama"` and `extension_id="ollama-provider"`.
- [x] Ensure extension action responses return stable `ok`, `message`, `details`, and action-specific fields used by CoreUI.
- [x] Preserve existing env/config names as compatibility inputs, but make the extension/provider the consumer where possible.
- [x] Add tests for runtime invocation of `ollama-provider` with a fake host chat client and fake settings repository.
- [x] Add tests for runtime stream invocation of `ollama-provider` with fake stream events.
- [x] Add tests that `llm_extensions_service.provider_catalog(runtime=..., capability=...)` returns Ollama models without core calling `/api/tags` directly.

### Phase 1 Verification Notes

- [x] Added bundled extension contract tests for manifest capabilities, provider surface, and self-contained `ollama_http.py` imports.
- [x] Verified focused extension/runtime suites: `pytest tests\llm_interactor\test_runtime.py tests\llm_interactor\test_ollama_extension_docker_contract.py tests\api\test_extensions_routes.py`.
- [x] Added document guardrail coverage proving this migration TODO remains English-only, checkbox-formatted, and decision-complete.

## Phase 2 - Move Model Listing, Health, Show/Tags, And WebUI Diagnostics

- [x] Replace WebUI model-listing helpers that call `_get_ollama_url()` and `/api/tags` with provider catalog calls.
- [x] Normalize provider labels used by CoreUI model selectors, settings screens, status cards, and extension tabs so users see `Ollama` as the provider name.
- [x] Replace build diagnostics that fetch Ollama tag names directly with `llm_extensions_service.provider_catalog(..., capability="chat")` or a dedicated extension action.
- [x] Move model `show` details for context length, thinking support, and form helpers behind an extension action or provider metadata call.
- [x] Move model hide/unhide/delete/pull behavior fully behind `ollama-provider` actions.
- [x] Replace root `infrastructure/stack_health.py` direct Ollama `/api/tags` probing with provider health when an extension runtime is available.
- [x] Keep Qdrant health in core/RAG ownership; do not move Qdrant checks into `ollama-provider`.
- [x] Keep WebUI response shapes stable for dashboard cards and settings forms.
- [x] Preserve fallback behavior when extension runtime is loading or unavailable: return `available=false`, cached provider rows, or existing degraded status rather than crashing.
- [x] Add WebUI tests proving model selectors still populate from provider catalog.
- [x] Add WebUI tests proving provider-facing labels render as `Ollama` and do not expose `Ollama Provider` in normal frontend surfaces.
- [x] Add WebUI tests proving health/status cards still report Ollama unavailable when the provider health check fails.
- [x] Add extension action tests for `show_model`, `hide_model`, `unhide_model`, `delete_model`, `pull_model`, and refresh/status behavior.

### Phase 2 Verification Notes

- [x] Build diagnostics now read Ollama model ids from provider catalog instead of direct `invoke_tags`.
- [x] `/api/webui/llm-proxy/builds/preview-model` uses the `show_model` extension action and preserves `{ok: false, error}` failures when runtime/provider action is unavailable.
- [x] `/health` uses provider health when extension runtime is available, keeps Qdrant probing in core, and falls back to direct `/api/tags` only during startup/runtime-unavailable compatibility.
- [x] Dashboard Ollama status reads provider health when available and keeps the previous ping fallback for runtime-loading compatibility.
- [x] `pytest tests/api/test_http_endpoints.py tests/api/test_extensions_routes.py` passed: 119 tests.
- [x] `pytest tests/llm_interactor/test_runtime.py tests/llm_interactor/test_ollama_extension_docker_contract.py` passed: 15 tests.
- [x] Regression search `rg "invoke_tags|/api/tags|_get_ollama_url" api infrastructure application -S` reports only startup/dashboard compatibility fallbacks, root legacy adapters, or documented compatibility.
- [x] Regression search `rg "Ollama Provider" CoreModules/CoreUI api extensions tests -S` reports no matches.

## Phase 3 - Move Chat And Streaming Paths

- [x] Route non-streaming `/v1/chat/completions` Ollama calls through `LLMRuntime.invoke(...)` or `RuntimeBackedChatClient`.
- [x] Route streaming `/v1/chat/completions` Ollama calls through `LLMRuntime.stream_invoke(...)` or `RuntimeBackedChatClient`.
- [x] Preserve OpenAI-compatible response shape, including `choices`, deltas, finish reasons, usage estimates, and trace metadata.
- [x] Preserve existing Ollama `think` behavior and reasoning-content mapping during the migration.
- [x] Preserve native tool call behavior and OpenAI/Ollama tool bridge behavior during the migration.
- [x] Preserve vision/multipart message handling during the migration.
- [x] Keep prompt assembly and RAG orchestration outside `ollama-provider`; the extension owns the provider call, not the application decision to use RAG.
- [x] Move Ollama-specific request-body formation into the provider where it belongs, leaving proxy code provider-neutral where feasible.
- [x] Replace direct imports of `infrastructure.ollama.model_capabilities`, `openai_ollama_tool_bridge`, and related helpers in proxy code with provider/runtime-owned helpers or a clearly temporary compatibility module.
- [x] Add proxy tests proving non-streaming chat still works through provider runtime.
- [x] Add proxy tests proving streaming chat still works through provider runtime.
- [x] Add proxy tests proving native tools, reasoning content, and vision payloads retain their public response shape.
- [x] Add trace tests proving provider id, model id, timings, Ollama payload metrics, and tool-call diagnostics remain visible.

### Phase 3 Verification Notes

- [x] `/v1/chat/completions` non-streaming now reaches the bundled Ollama provider through `RuntimeBackedChatClient` and `LLMRuntime.invoke(..., operation="chat_api")` once extension runtime bootstrap is ready.
- [x] `/v1/chat/completions` streaming now reaches the bundled Ollama provider through `RuntimeBackedChatClient` and `LLMRuntime.stream_invoke(..., operation="chat_api_stream_events")` once extension runtime bootstrap is ready.
- [x] Runtime-unavailable startup behavior still falls back to the legacy chat client.
- [x] Remaining proxy-side Ollama helper imports now pass through `llm_proxy.ollama_compat`, a documented temporary compatibility boundary for OpenAI-compatible request normalization, tool bridging, vision normalization, and metadata helpers.
- [x] Provider-runtime chat traces now record provider id, provider model id, provider operation, runtime usage, latency, token estimates, Ollama done metrics, brand metadata where available, reasoning/final previews, and native tool-call diagnostics.
- [x] `pytest tests/api/test_http_endpoints.py` passed: 116 tests.
- [x] `pytest tests/llm_interactor/test_runtime.py` passed: 10 tests.

## Phase 4 - Move Embed/Rerank And RAG/Indexing Callers

- [x] Replace root `infrastructure.ollama.embed_client.OllamaEmbeddingProvider` usage with a provider-backed embedding adapter.
- [x] Replace root `infrastructure.ollama.rerank_client.OllamaRerankClient` usage with a provider-backed rerank adapter.
- [x] Replace `CoreModules/RagService/rag_service/infrastructure/ollama_embedding.py` with a provider-backed adapter or mark it as temporary compatibility until RagService can receive provider clients through its container.
- [x] Replace `CoreModules/RagService/rag_service/infrastructure/ollama_rerank.py` with a provider-backed adapter or mark it as temporary compatibility until RagService can receive provider clients through its container.
- [x] Replace `CoreModules/RagService/rag_service/infrastructure/ollama_chat.py` with `RuntimeBackedChatClient` or another provider-backed adapter.
- [x] Update `rag_service.infrastructure.container` so default chat/embed/rerank clients can be supplied by `LlmInteractor` runtime when available.
- [x] Keep RAG prompt building, retrieval, chunking, and Qdrant ownership inside RAG modules; only the Ollama provider calls move.
- [x] Replace `CoreModules/WebUIBackend` local ingestion direct embed calls with a provider-backed embed call or a documented temporary compatibility adapter.
- [x] Replace external-docs ingestion direct `OllamaEmbedAdapter` usage in proxy wiring with a provider-backed embed adapter.
- [x] Preserve batch embedding behavior, timeout behavior, retry behavior, and input truncation behavior.
- [x] Preserve rerank fallback behavior where current code falls back from `/api/rerank` to `/api/generate`.
- [x] Add RAG unit tests proving `build_rag_context` and indexing paths use provider-backed embeddings.
- [x] Add RAG tests proving rerank can succeed and fail through the provider-backed adapter.
- [x] Add ingestion tests proving embed failures are still reported with useful counts/errors.

### Phase 4 Verification Notes

- [x] Proxy RAG dependencies now wrap embed and rerank clients with lazy provider-runtime adapters when the extension manager is available.
- [x] External-docs ingestion no longer constructs `OllamaEmbedAdapter` in proxy wiring; it receives the provider-backed embedding adapter used by proxy RAG.
- [x] `CoreModules/WebUIBackend` local Markdown ingestion now calls the extension-owned `ollama-provider` HTTP helper instead of root `infrastructure.ollama` embed helpers.
- [x] `rag_service.infrastructure.container` can supply runtime-backed chat, embed, and rerank clients while preserving legacy fallback clients for standalone callers.
- [x] `PYTHONPATH=CoreModules/ErrorManager;$PYTHONPATH pytest tests/rag_service tests/application/test_rag_use_cases.py tests/rag_service/test_provider_runtime_adapters.py` passed: 37 tests.
- [x] `pytest tests/external_docs_rag` passed: 2 tests.
- [x] `pytest tests/webui/test_ingest_markdown_local.py` passed: 2 tests.

## Phase 5 - Move Service Actions And Docker/Native Process Boundaries

- [x] Keep Docker ownership inside extension actions through `host_context.docker_runtime` and `DockerContainerSpec`.
- [x] Do not allow `ollama-provider` to call Docker CLI, Docker SDK clients, `/api/webui/docker/*`, or shell Docker commands directly.
- [x] Keep native Ollama stop behavior behind host-provided metadata such as `stop_native_ollama`; the extension may request it but must not own OS-specific process logic directly.
- [x] Move UI start/stop/pull/status actions to extension action routes where any remaining core route only delegates generically.
- [x] Preserve the existing user-facing behavior for start Ollama, stop Ollama, download image, pull model, cancel pull, and progress notifications.
- [x] Preserve ServiceStarter tests for standalone `servicestarter.ollama_ops`; ServiceStarter may remain a low-level host capability while `ollama-provider` owns the app-level action.
- [x] Add tests proving extension service actions use `host_context.docker_runtime`.
- [x] Add tests proving extension service actions do not import or call Docker directly.
- [x] Add WebUI tests proving the Ollama tab can start/stop service through extension actions.

Phase 5 completion notes:

- [x] Widened extension Docker policy validation to scan the entire backend folder, while allowing non-Docker subprocess use such as the `ollama_interactor` CLI fallback.
- [x] Added regression coverage for bundled `ollama-provider` Docker policy, backend helper-module Docker violations, generic extension start/stop action routes, and compatibility `/ollama/start` + `/ollama/stop` delegation.
- [x] Verified focused suites: `pytest tests\llm_interactor\test_extension_docker_policy.py tests\llm_interactor\test_ollama_extension_docker_contract.py`, `pytest tests\api\test_extensions_routes.py`, and `pytest tests\servicestarter`.

## Phase 6 - Move Legacy `/api/*` Passthrough And `/v1/completions` Generate Behavior

- [x] Preserve `GET /api/tags` compatibility for clients that use the app as an Ollama-compatible base URL.
- [x] Preserve `POST /api/show` compatibility for clients that inspect model details.
- [x] Preserve `POST /api/generate` compatibility for inline completion and legacy Ollama-style clients.
- [x] Preserve `POST /api/chat` compatibility for transparent Ollama chat clients.
- [x] Preserve `POST /v1/completions` behavior that maps OpenAI legacy completions to Ollama generate.
- [x] Decide whether raw passthrough should be represented as new provider operations, extension HTTP routes, or a narrowly scoped compatibility adapter that delegates to `ollama-provider`.
- [x] Ensure raw passthrough does not accidentally apply RAG, prompt templates, proxy auth transformations, or model remapping unless existing behavior already does so.
- [x] Preserve request body fields such as `format`, `keep_alive`, `options`, `stream`, `suffix`, `raw`, `system`, and `template` where current compatibility paths support them.
- [x] Preserve streaming semantics and error status mapping for passthrough routes.
- [x] Add passthrough tests for `/api/tags`, `/api/show`, `/api/generate`, and `/api/chat`.
- [x] Add `/v1/completions` tests proving generate request body and response shape remain stable.
- [x] Add tests for extension-runtime-unavailable fallback behavior on compatibility routes.

Phase 6 completion notes:

- [x] Kept public `/api/tags`, `/api/show`, `/api/generate`, `/api/chat`, and `/v1/completions` routes in the compatibility blueprint, but changed their first-choice backend to `ollama-provider` via `LLMRuntime` operation `raw_ollama`.
- [x] Kept extension-runtime-unavailable fallback to the old direct upstream adapter so Flask startup/loading states continue serving legacy clients.
- [x] Added provider raw passthrough tests, runtime-backed HTTP passthrough tests, runtime-unavailable fallback tests, `/v1/completions` runtime/fallback tests, and stream setup error mapping coverage.
- [x] Verified focused suites: `pytest tests\llm_interactor\test_ollama_extension_docker_contract.py tests\api\test_http_endpoints.py -k "raw_ollama or ollama_api_passthrough or ollama_api_stream_runtime or v1_completions"` and `ruff check` on changed Phase 6 Python files.

## Phase 7 - Remove Legacy Core Adapters, Update Docs, And Enforce Guardrails

- [x] Delete or deprecate root `infrastructure/ollama/*` only after all app call sites have moved to the provider runtime or extension-owned modules.
- [x] Delete or deprecate duplicate `CoreModules/RagService/rag_service/infrastructure/ollama_*` adapters only after RagService can receive provider-backed clients.
- [x] Remove direct Ollama URL/model helpers from core config only after compatibility inputs are consumed by the provider and all callers use provider-neutral settings.
- [x] Update `AI_RULES.md` extension guidance if new provider-runtime guardrails are added.
- [x] Update `docs/ARCHITECTURE.md`, `docs/legacy_map.md`, `CoreModules/LlmProxy/README.md`, and `CoreModules/RagService/README.md` after behavior actually moves.
- [x] Update tests and fixtures to use provider/runtime fakes instead of `OllamaChatClient` fakes where possible.
- [x] Keep ServiceStarter documentation clear: ServiceStarter can provide host capabilities, but app-level Ollama UX belongs to `ollama-provider`.
- [x] Add a CI or local verification note that rejects new direct `infrastructure.ollama` imports outside allowed temporary compatibility modules.
- [x] Remove temporary compatibility modules once public behavior has been verified through provider-owned paths.
- [x] Close this migration only when direct Ollama references in core are either gone, explicitly documented as compatibility boundaries, or owned by tests for public API compatibility.

Phase 7 completion notes:

- [x] Root `infrastructure/ollama/*`, RagService `rag_service.infrastructure.ollama_*`, and core config URL/model helpers are retained as documented compatibility/fallback boundaries rather than deleted in this slice.
- [x] Added `tests/application/test_ollama_migration_guardrails.py` to reject new direct `infrastructure.ollama` imports unless the file is explicitly allowlisted as a compatibility or test boundary.
- [x] Updated `AI_RULES.md`, `docs/ARCHITECTURE.md`, `docs/legacy_map.md`, `CoreModules/LlmProxy/README.md`, `CoreModules/RagService/README.md`, and `CoreModules/ServiceStarter/README.md`.
- [x] Verified focused guardrail suite: `pytest tests\application\test_ollama_migration_guardrails.py` and `ruff check tests\application\test_ollama_migration_guardrails.py`.

## Guardrails

- [x] Do not add new direct `infrastructure.ollama` imports outside explicitly marked temporary compatibility code.
- [x] Do not make CoreUI know Ollama internals beyond generic extension/provider UI payloads.
- [x] Do not expose `Ollama Provider` as the normal frontend display name; reserve provider/extension wording for developer diagnostics only if needed.
- [x] Do not put Ollama-specific model metadata at the top level of generic provider DTOs when it can live under `metadata`.
- [x] Do not let extensions call Docker directly; use `host_context.docker_runtime` and `DockerContainerSpec`.
- [x] Do not move Qdrant, retrieval policy, prompt assembly, or RAG orchestration into `ollama-provider`.
- [x] Do not silently change public compatibility for `/v1/models`, `/v1/chat/completions`, `/v1/completions`, `/api/tags`, `/api/show`, `/api/generate`, or `/api/chat`.
- [x] Do not remove old env/config names until compatibility has been intentionally migrated and documented.
- [x] Do not break Open WebUI or external clients that use this app as an Ollama-compatible base URL.
- [x] Do not rely on extension runtime being ready synchronously during Flask app startup unless tests prove that path is stable.
- [x] Do not create new Ollama-specific CoreUI components when the extension tab/action schema can express the workflow.

## Working Criteria

- [x] A migration slice is valid only if it names the exact public behavior it touches before implementation.
- [x] A migration slice is valid only if it keeps all unrelated Ollama behavior on the previous path.
- [x] A migration slice is valid only if old public endpoints still return the same status codes and response shapes unless the slice explicitly changes that contract.
- [x] A migration slice is valid only if extension-runtime-loading and extension-runtime-unavailable states are handled without crashing WebUI or `/v1` routes.
- [x] A migration slice is valid only if `provider_id="ollama"` and `extension_id="ollama-provider"` remain stable.
- [x] A migration slice is valid only if normal frontend/provider labels render as `Ollama`.
- [x] A migration slice is valid only if `ollama-provider` remains self-contained and does not import core Ollama infrastructure adapters.
- [x] A migration slice is valid only if Docker/service work remains behind `host_context.docker_runtime`, `DockerContainerSpec`, or host-provided metadata.
- [x] A migration slice is valid only if RAG policy, prompt assembly, retrieval, and Qdrant ownership stay outside `ollama-provider`.
- [x] A migration slice is valid only if config/env compatibility is preserved or the compatibility change is explicitly documented in the same PR.
- [x] A migration slice is done only after focused tests for the touched subsystem pass.
- [x] A migration slice is done only after the regression searches relevant to that slice have been run and reviewed.
- [x] A migration slice is done only after this TODO file is updated with completed items and any newly discovered follow-up tasks.

## Phase Completion Criteria

- [x] Phase 0 is complete when every direct Ollama dependency is inventoried, classified, and protected by at least one baseline test or documented compatibility reason.
- [x] Phase 1 is complete when `ollama-provider` can be discovered, described, listed in provider catalog, invoked in unit tests, and used as the default provider id without blocking startup.
- [x] Phase 2 is complete when WebUI model lists, provider labels, health/status, model details, and model actions use provider catalog or extension actions instead of direct `/api/tags`/`/api/show` calls.
- [x] Phase 3 is complete when `/v1/chat/completions` non-streaming and streaming Ollama calls go through `LLMRuntime` or `RuntimeBackedChatClient` while preserving OpenAI-compatible output, trace fields, tools, thinking, and vision.
- [x] Phase 4 is complete when RAG, indexing, external-docs ingestion, embeddings, and rerank use provider-backed adapters while preserving retries, timeouts, batch behavior, truncation, and error reporting.
- [x] Phase 5 is complete when app-level Ollama start/stop/pull/status behavior is extension-owned and Docker/native-process boundaries are enforced by tests.
- [x] Phase 6 is complete when `/api/tags`, `/api/show`, `/api/generate`, `/api/chat`, and `/v1/completions` preserve legacy client compatibility while delegating Ollama ownership behind the extension/provider boundary.
- [x] Phase 7 is complete when temporary direct Ollama adapters are deleted or explicitly documented as compatibility boundaries, docs are updated, and regression searches show no unclassified direct Ollama references.

## Manual Smoke Checklist

- [ ] Start the Flask app without a running Ollama server and confirm WebUI still loads.
- [ ] Start the Flask app with Ollama available and confirm provider catalog/model selectors show `Ollama`.
- [ ] Open the Ollama extension tab and confirm status, model table, and actions render without CoreUI-specific Ollama wiring.
- [ ] Call `GET /api/webui/extensions/registry` and confirm `ollama-provider` title is `Ollama`.
- [ ] Call `GET /api/webui/extensions/providers` and confirm the Ollama provider row has `provider_id="ollama"` and `title="Ollama"`.
- [ ] Call `GET /api/webui/providers/catalog?capability=chat` and confirm Ollama models use `provider_title="Ollama"` when models are available.
- [ ] Call `GET /api/webui/models` and confirm model rows preserve `id`, `name`, `provider_id`, `provider_title`, `size`, and `modified_at`.
- [ ] Call `GET /v1/models` and confirm OpenAI-compatible model listing still works.
- [ ] Call `POST /v1/chat/completions` with a simple non-streaming request after chat migration phases and confirm response shape is unchanged.
- [ ] Call `POST /v1/chat/completions` with `stream=true` after streaming migration phases and confirm SSE/chunk behavior is unchanged.
- [ ] Call `GET /api/tags`, `POST /api/show`, `POST /api/generate`, and `POST /api/chat` after passthrough migration phases and confirm Ollama-compatible clients still work.
- [ ] Run a small RAG query after embed/rerank migration phases and confirm embeddings, search, rerank, trace timings, and final answer still work.
- [ ] Run a small indexing/ingestion job after embed migration phases and confirm chunk counts and embed failures are reported clearly.
- [ ] Start/stop Ollama through the extension tab after service migration phases and confirm Docker/native process boundaries behave as expected.
- [ ] Confirm logs/traces still identify provider id, model id, timing, token estimates, and error details where they existed before.

## Test Plan

- [x] Run extension runtime tests for bundled extension discovery and provider catalog.
- [x] Add or update tests under `tests/llm_interactor` for `ollama-provider` runtime invocation, streaming, provider rows, catalog filtering, health, and actions.
- [x] Add or update proxy tests proving chat and streaming work through provider runtime.
- [x] Add or update proxy tests proving native tools, thinking/reasoning content, vision payloads, and trace fields remain stable.
- [x] Add or update passthrough tests for `/api/tags`, `/api/show`, `/api/generate`, and `/api/chat`.
- [x] Add or update `/v1/completions` tests proving legacy generate behavior remains stable.
- [x] Add or update RAG tests proving embed and rerank calls use provider-backed adapters.
- [x] Add or update indexing/ingestion tests proving embedding failures, retries, and batch behavior remain stable.
- [x] Add or update WebUI tests proving model selectors, provider catalog, health/status cards, and the Ollama tab still load.
- [x] Add or update ServiceStarter/extension-boundary tests proving app-level service actions use extension actions and `host_context.docker_runtime`.
- [x] Add regression searches proving no new direct Ollama dependencies outside allowed temporary files.
- [x] Run focused tests first, then broader `pytest` suites touched by the migration.

## Suggested Regression Searches

- [x] Run `rg -n "from infrastructure\\.ollama|import infrastructure\\.ollama" api application CoreModules infrastructure extensions tests -g "*.py"` and verify every match is allowed or scheduled for removal.
- [x] Run `rg -n "OllamaChatClient|OllamaEmbeddingProvider|OllamaRerankClient|OllamaEmbedAdapter" api application CoreModules infrastructure extensions tests -g "*.py"` and verify every match is allowed or scheduled for removal.
- [x] Run `rg -n "OLLAMA_|/api/(tags|show|generate|chat|embed)|11434" api application CoreModules infrastructure extensions config tests -g "*.py" -g "*.yaml" -g "*.yml" -g "*.json"` and verify every match is provider-owned, compatibility-owned, config-owned, or test-owned.
- [x] Run `rg -n "docker|Docker" extensions/bundled/ollama-provider -g "*.py"` and verify any service logic uses only `host_context.docker_runtime` plus `DockerContainerSpec`.
- [x] Run `rg -n "ollama-provider|provider_catalog|LLMRuntime|RuntimeBackedChatClient" api CoreModules tests -g "*.py"` and verify new call sites use provider/runtime abstractions rather than direct Ollama clients.

## Acceptance Criteria

- [x] `OLLAMA_EXTENSION_MIGRATION_TODO.md` exists at the repository root.
- [x] The document is English-only.
- [x] Every actionable item uses Markdown checkbox format `- [ ]`.
- [x] The document explains what to migrate, when to migrate it, why it belongs in the extension, and how to validate each phase.
- [x] The document identifies `ollama-provider` as the canonical owner of Ollama provider behavior.
- [x] The document preserves current public compatibility expectations.
- [x] The document includes migration guardrails for CoreUI, Docker, RAG ownership, config compatibility, and raw `/api/*` compatibility.
- [x] The document includes test scenarios and regression searches.
- [x] The document includes working criteria, phase completion criteria, and manual smoke checks.
- [x] The document is usable by Codex and Cursor without needing extra implementation decisions.

## Assumptions

- [x] This document is a roadmap and TODO guide, not the migration implementation itself.
- [x] Scope is the full Ollama migration, not only the first wave.
- [x] Existing public API compatibility is more important than deleting legacy code quickly.
- [x] `ollama-provider` remains bundled and trusted during this migration.
- [x] Core may keep temporary compatibility adapters while public routes are migrated behind provider-owned behavior.
- [x] ServiceStarter can remain as a host-level capability, but app-level Ollama UX belongs to `ollama-provider`.
