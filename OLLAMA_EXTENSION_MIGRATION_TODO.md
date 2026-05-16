# Ollama Extension Migration TODO

This document is the decision-complete migration guide for moving Ollama-owned behavior out of core and monolith paths into the bundled `ollama-provider` extension. It is intended for Codex, Cursor, and humans working in this repository.

## Why This Exists

Ollama is already represented as a bundled extension at `extensions/bundled/ollama-provider`, and that extension already advertises provider capabilities such as chat, streaming, embeddings, rerank, model listing, health, tab UI, and service actions.

Core still contains direct Ollama knowledge across proxy wiring, WebUI routes, RAG infrastructure, health checks, service control, config helpers, compatibility routes, and tests. That makes the app harder to modularize because core must understand Ollama URLs, Ollama request shapes, Ollama model metadata, Ollama service lifecycle, and Ollama-specific failure modes.

Target state: `ollama-provider` owns Ollama behavior. Core talks through provider-neutral `LlmInteractor` contracts, extension actions, and temporary compatibility adapters only where public API compatibility requires them during migration.

## Current Baseline

- [ ] Confirm `extensions/bundled/ollama-provider/chironai-extension.json` declares `chat`, `embed`, `rerank`, `streaming`, `tools`, `vision`, `model_listing`, `health_check`, `tab_ui`, and `service_actions`.
- [ ] Confirm `extensions/bundled/ollama-provider/backend/provider.py` implements provider invocation for chat, streaming, embed, rerank, model listing, health, tab payloads, model actions, pull/delete/hide/show, and service actions.
- [ ] Confirm `extensions/bundled/ollama-provider/backend/ollama_http.py` is self-contained and does not import core `infrastructure.*` Ollama adapters.
- [ ] Inventory direct Ollama imports and calls in `api/`, especially `api/http/webui_routes.py`, `api/http/webui_llm_proxy_routes.py`, `api/http/webui_crawler_routes.py`, `api/http/llm_proxy_wiring.py`, and `api/http/rag_routes.py`.
- [ ] Inventory direct Ollama imports and calls in `CoreModules/LlmProxy`, especially chat completions, legacy completions, upstream passthrough, model metadata, tool bridging, and `/api/*` compatibility routes.
- [ ] Inventory direct Ollama imports and calls in `CoreModules/RagService`, especially `rag_service/infrastructure/ollama_chat.py`, `ollama_embedding.py`, `ollama_rerank.py`, `runtime.py`, `config.py`, and the RAG application wiring.
- [ ] Inventory direct Ollama imports and calls in root `infrastructure/`, especially `infrastructure/ollama/*` and `infrastructure/stack_health.py`.
- [ ] Inventory direct Ollama imports and calls in `CoreModules/WebUIBackend`, especially local ingestion paths that call embed directly.
- [ ] Inventory tests that depend on direct Ollama names, modules, or request shapes, including proxy, RAG, config, infrastructure, ServiceStarter, and extension runtime tests.
- [ ] Classify every discovered dependency as `keep temporarily`, `move to extension`, `replace with provider runtime`, or `delete after migration`.
- [ ] Record the classification near the relevant migration phase in this document before editing behavior.

## Ownership Target

- [ ] Treat `ollama-provider` as the canonical owner of Ollama HTTP/CLI calls.
- [ ] Treat `ollama-provider` as the canonical owner of model catalog, model visibility, show/delete/pull actions, and model metadata.
- [ ] Treat `ollama-provider` as the canonical owner of Ollama provider health and service diagnostics.
- [ ] Treat `ollama-provider` as the canonical owner of Ollama embed and rerank clients.
- [ ] Treat `ollama-provider` as the canonical owner of Ollama service start/stop UI actions.
- [ ] Treat `ollama-provider` as the canonical owner of Ollama-specific capability probing, including thinking/tool/vision metadata when that metadata comes from Ollama.
- [ ] Make core call Ollama through `LLMRuntime.invoke(...)` for non-streaming provider operations.
- [ ] Make core call Ollama through `LLMRuntime.stream_invoke(...)` for streaming provider operations.
- [ ] Make WebUI/provider actions call Ollama through `llm_extensions_service.run_extension_action(...)`.
- [ ] Use `RuntimeBackedChatClient` and other compatibility adapters only as temporary migration bridges.
- [ ] Preserve public HTTP compatibility while moving ownership behind the scenes.

## Phase 0 - Audit And Behavior Lock

- [ ] Run the direct-dependency inventory before changing implementation code.
- [ ] Add or update tests that pin current public behavior for `/v1/models`, `/v1/chat/completions`, `/v1/completions`, `/api/tags`, `/api/show`, `/api/generate`, and `/api/chat`.
- [ ] Add or update tests that pin current WebUI behavior for provider catalog, model selectors, Ollama tab loading, model visibility, pull progress, and health/status cards.
- [ ] Add or update tests that pin current RAG behavior for chat, embeddings, rerank, indexing, and RAG test runner paths.
- [ ] Add or update tests that pin current service behavior for starting/stopping Ollama through the UI and through ServiceStarter-adjacent helpers.
- [ ] Capture current env/config compatibility expectations for `OLLAMA_BASE_URL`, `OLLAMA_CHAT_URL`, `OLLAMA_URL`, `OLLAMA_EMBED_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `OLLAMA_RERANK_MODEL`, `OLLAMA_EMBED_TIMEOUT`, `LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL`, and related YAML model settings.
- [ ] Define the allowed temporary direct-Ollama files for the next phase before adding any new compatibility code.
- [ ] Add a regression search command to the final verification notes for each PR that touches Ollama migration.

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

## Phase 2 - Move Model Listing, Health, Show/Tags, And WebUI Diagnostics

- [ ] Replace WebUI model-listing helpers that call `_get_ollama_url()` and `/api/tags` with provider catalog calls.
- [x] Normalize provider labels used by CoreUI model selectors, settings screens, status cards, and extension tabs so users see `Ollama` as the provider name.
- [ ] Replace build diagnostics that fetch Ollama tag names directly with `llm_extensions_service.provider_catalog(..., capability="chat")` or a dedicated extension action.
- [ ] Move model `show` details for context length, thinking support, and form helpers behind an extension action or provider metadata call.
- [ ] Move model hide/unhide/delete/pull behavior fully behind `ollama-provider` actions.
- [ ] Replace root `infrastructure/stack_health.py` direct Ollama `/api/tags` probing with provider health when an extension runtime is available.
- [ ] Keep Qdrant health in core/RAG ownership; do not move Qdrant checks into `ollama-provider`.
- [ ] Keep WebUI response shapes stable for dashboard cards and settings forms.
- [ ] Preserve fallback behavior when extension runtime is loading or unavailable: return `available=false`, cached provider rows, or existing degraded status rather than crashing.
- [ ] Add WebUI tests proving model selectors still populate from provider catalog.
- [x] Add WebUI tests proving provider-facing labels render as `Ollama` and do not expose `Ollama Provider` in normal frontend surfaces.
- [ ] Add WebUI tests proving health/status cards still report Ollama unavailable when the provider health check fails.
- [ ] Add extension action tests for `show_model`, `hide_model`, `unhide_model`, `delete_model`, `pull_model`, and refresh/status behavior.

## Phase 3 - Move Chat And Streaming Paths

- [ ] Route non-streaming `/v1/chat/completions` Ollama calls through `LLMRuntime.invoke(...)` or `RuntimeBackedChatClient`.
- [ ] Route streaming `/v1/chat/completions` Ollama calls through `LLMRuntime.stream_invoke(...)` or `RuntimeBackedChatClient`.
- [ ] Preserve OpenAI-compatible response shape, including `choices`, deltas, finish reasons, usage estimates, and trace metadata.
- [ ] Preserve existing Ollama `think` behavior and reasoning-content mapping during the migration.
- [ ] Preserve native tool call behavior and OpenAI/Ollama tool bridge behavior during the migration.
- [ ] Preserve vision/multipart message handling during the migration.
- [ ] Keep prompt assembly and RAG orchestration outside `ollama-provider`; the extension owns the provider call, not the application decision to use RAG.
- [ ] Move Ollama-specific request-body formation into the provider where it belongs, leaving proxy code provider-neutral where feasible.
- [ ] Replace direct imports of `infrastructure.ollama.model_capabilities`, `openai_ollama_tool_bridge`, and related helpers in proxy code with provider/runtime-owned helpers or a clearly temporary compatibility module.
- [ ] Add proxy tests proving non-streaming chat still works through provider runtime.
- [ ] Add proxy tests proving streaming chat still works through provider runtime.
- [ ] Add proxy tests proving native tools, reasoning content, and vision payloads retain their public response shape.
- [ ] Add trace tests proving provider id, model id, timings, Ollama payload metrics, and tool-call diagnostics remain visible.

## Phase 4 - Move Embed/Rerank And RAG/Indexing Callers

- [ ] Replace root `infrastructure.ollama.embed_client.OllamaEmbeddingProvider` usage with a provider-backed embedding adapter.
- [ ] Replace root `infrastructure.ollama.rerank_client.OllamaRerankClient` usage with a provider-backed rerank adapter.
- [ ] Replace `CoreModules/RagService/rag_service/infrastructure/ollama_embedding.py` with a provider-backed adapter or mark it as temporary compatibility until RagService can receive provider clients through its container.
- [ ] Replace `CoreModules/RagService/rag_service/infrastructure/ollama_rerank.py` with a provider-backed adapter or mark it as temporary compatibility until RagService can receive provider clients through its container.
- [ ] Replace `CoreModules/RagService/rag_service/infrastructure/ollama_chat.py` with `RuntimeBackedChatClient` or another provider-backed chat adapter.
- [ ] Update `rag_service.infrastructure.container` so default chat/embed/rerank clients can be supplied by `LlmInteractor` runtime when available.
- [ ] Keep RAG prompt building, retrieval, chunking, and Qdrant ownership inside RAG modules; only the Ollama provider calls move.
- [ ] Replace `CoreModules/WebUIBackend` local ingestion direct embed calls with a provider-backed embed call or a documented temporary compatibility adapter.
- [ ] Replace external-docs ingestion direct `OllamaEmbedAdapter` usage in proxy wiring with a provider-backed embed adapter.
- [ ] Preserve batch embedding behavior, timeout behavior, retry behavior, and input truncation behavior.
- [ ] Preserve rerank fallback behavior where current code falls back from `/api/rerank` to `/api/generate`.
- [ ] Add RAG unit tests proving `build_rag_context` and indexing paths use provider-backed embeddings.
- [ ] Add RAG tests proving rerank can succeed and fail through the provider-backed adapter.
- [ ] Add ingestion tests proving embed failures are still reported with useful counts/errors.

## Phase 5 - Move Service Actions And Docker/Native Process Boundaries

- [ ] Keep Docker ownership inside extension actions through `host_context.docker_runtime` and `DockerContainerSpec`.
- [ ] Do not allow `ollama-provider` to call Docker CLI, Docker SDK clients, `/api/webui/docker/*`, or shell Docker commands directly.
- [ ] Keep native Ollama stop behavior behind host-provided metadata such as `stop_native_ollama`; the extension may request it but must not own OS-specific process logic directly.
- [ ] Move UI start/stop/pull/status actions to extension action routes where any remaining core route only delegates generically.
- [ ] Preserve the existing user-facing behavior for start Ollama, stop Ollama, download image, pull model, cancel pull, and progress notifications.
- [ ] Preserve ServiceStarter tests for standalone `servicestarter.ollama_ops`; ServiceStarter may remain a low-level host capability while `ollama-provider` owns the app-level action.
- [ ] Add tests proving extension service actions use `host_context.docker_runtime`.
- [ ] Add tests proving extension service actions do not import or call Docker directly.
- [ ] Add WebUI tests proving the Ollama tab can start/stop service through extension actions.

## Phase 6 - Move Legacy `/api/*` Passthrough And `/v1/completions` Generate Behavior

- [ ] Preserve `GET /api/tags` compatibility for clients that use the app as an Ollama-compatible base URL.
- [ ] Preserve `POST /api/show` compatibility for clients that inspect model details.
- [ ] Preserve `POST /api/generate` compatibility for inline completion and legacy Ollama-style clients.
- [ ] Preserve `POST /api/chat` compatibility for transparent Ollama chat clients.
- [ ] Preserve `POST /v1/completions` behavior that maps OpenAI legacy completions to Ollama generate.
- [ ] Decide whether raw passthrough should be represented as new provider operations, extension HTTP routes, or a narrowly scoped compatibility adapter that delegates to `ollama-provider`.
- [ ] Ensure raw passthrough does not accidentally apply RAG, prompt templates, proxy auth transformations, or model remapping unless existing behavior already does so.
- [ ] Preserve request body fields such as `format`, `keep_alive`, `options`, `stream`, `suffix`, `raw`, `system`, and `template` where current compatibility paths support them.
- [ ] Preserve streaming semantics and error status mapping for passthrough routes.
- [ ] Add passthrough tests for `/api/tags`, `/api/show`, `/api/generate`, and `/api/chat`.
- [ ] Add `/v1/completions` tests proving generate request body and response shape remain stable.
- [ ] Add tests for extension-runtime-unavailable fallback behavior on compatibility routes.

## Phase 7 - Remove Legacy Core Adapters, Update Docs, And Enforce Guardrails

- [ ] Delete or deprecate root `infrastructure/ollama/*` only after all app call sites have moved to the provider runtime or extension-owned modules.
- [ ] Delete or deprecate duplicate `CoreModules/RagService/rag_service/infrastructure/ollama_*` adapters only after RagService can receive provider-backed clients.
- [ ] Remove direct Ollama URL/model helpers from core config only after compatibility inputs are consumed by the provider and all callers use provider-neutral settings.
- [ ] Update `AI_RULES.md` extension guidance if new provider-runtime guardrails are added.
- [ ] Update `docs/ARCHITECTURE.md`, `docs/legacy_map.md`, `CoreModules/LlmProxy/README.md`, and `CoreModules/RagService/README.md` after behavior actually moves.
- [ ] Update tests and fixtures to use provider/runtime fakes instead of `OllamaChatClient` fakes where possible.
- [ ] Keep ServiceStarter documentation clear: ServiceStarter can provide host capabilities, but app-level Ollama UX belongs to `ollama-provider`.
- [ ] Add a CI or local verification note that rejects new direct `infrastructure.ollama` imports outside allowed temporary compatibility modules.
- [ ] Remove temporary compatibility modules once public behavior has been verified through provider-owned paths.
- [ ] Close this migration only when direct Ollama references in core are either gone, explicitly documented as compatibility boundaries, or owned by tests for public API compatibility.

## Guardrails

- [ ] Do not add new direct `infrastructure.ollama` imports outside explicitly marked temporary compatibility code.
- [ ] Do not make CoreUI know Ollama internals beyond generic extension/provider UI payloads.
- [ ] Do not expose `Ollama Provider` as the normal frontend display name; reserve provider/extension wording for developer diagnostics only if needed.
- [ ] Do not put Ollama-specific model metadata at the top level of generic provider DTOs when it can live under `metadata`.
- [ ] Do not let extensions call Docker directly; use `host_context.docker_runtime` and `DockerContainerSpec`.
- [ ] Do not move Qdrant, retrieval policy, prompt assembly, or RAG orchestration into `ollama-provider`.
- [ ] Do not silently change public compatibility for `/v1/models`, `/v1/chat/completions`, `/v1/completions`, `/api/tags`, `/api/show`, `/api/generate`, or `/api/chat`.
- [ ] Do not remove old env/config names until compatibility has been intentionally migrated and documented.
- [ ] Do not break Open WebUI or external clients that use this app as an Ollama-compatible base URL.
- [ ] Do not rely on extension runtime being ready synchronously during Flask app startup unless tests prove that path is stable.
- [ ] Do not create new Ollama-specific CoreUI components when the extension tab/action schema can express the workflow.

## Working Criteria

- [ ] A migration slice is valid only if it names the exact public behavior it touches before implementation.
- [ ] A migration slice is valid only if it keeps all unrelated Ollama behavior on the previous path.
- [ ] A migration slice is valid only if old public endpoints still return the same status codes and response shapes unless the slice explicitly changes that contract.
- [ ] A migration slice is valid only if extension-runtime-loading and extension-runtime-unavailable states are handled without crashing WebUI or `/v1` routes.
- [ ] A migration slice is valid only if `provider_id="ollama"` and `extension_id="ollama-provider"` remain stable.
- [ ] A migration slice is valid only if normal frontend/provider labels render as `Ollama`.
- [ ] A migration slice is valid only if `ollama-provider` remains self-contained and does not import core Ollama infrastructure adapters.
- [ ] A migration slice is valid only if Docker/service work remains behind `host_context.docker_runtime`, `DockerContainerSpec`, or host-provided metadata.
- [ ] A migration slice is valid only if RAG policy, prompt assembly, retrieval, and Qdrant ownership stay outside `ollama-provider`.
- [ ] A migration slice is valid only if config/env compatibility is preserved or the compatibility change is explicitly documented in the same PR.
- [ ] A migration slice is done only after focused tests for the touched subsystem pass.
- [ ] A migration slice is done only after the regression searches relevant to that slice have been run and reviewed.
- [ ] A migration slice is done only after this TODO file is updated with completed items and any newly discovered follow-up tasks.

## Phase Completion Criteria

- [ ] Phase 0 is complete when every direct Ollama dependency is inventoried, classified, and protected by at least one baseline test or documented compatibility reason.
- [ ] Phase 1 is complete when `ollama-provider` can be discovered, described, listed in provider catalog, invoked in unit tests, and used as the default provider id without blocking startup.
- [ ] Phase 2 is complete when WebUI model lists, provider labels, health/status, model details, and model actions use provider catalog or extension actions instead of direct `/api/tags`/`/api/show` calls.
- [ ] Phase 3 is complete when `/v1/chat/completions` non-streaming and streaming Ollama calls go through `LLMRuntime` or `RuntimeBackedChatClient` while preserving OpenAI-compatible output, trace fields, tools, thinking, and vision.
- [ ] Phase 4 is complete when RAG, indexing, external-docs ingestion, embeddings, and rerank use provider-backed adapters while preserving retries, timeouts, batch behavior, truncation, and error reporting.
- [ ] Phase 5 is complete when app-level Ollama start/stop/pull/status behavior is extension-owned and Docker/native-process boundaries are enforced by tests.
- [ ] Phase 6 is complete when `/api/tags`, `/api/show`, `/api/generate`, `/api/chat`, and `/v1/completions` preserve legacy client compatibility while delegating Ollama ownership behind the extension/provider boundary.
- [ ] Phase 7 is complete when temporary direct Ollama adapters are deleted or explicitly documented as compatibility boundaries, docs are updated, and regression searches show no unclassified direct Ollama references.

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

- [ ] Run extension runtime tests for bundled extension discovery and provider catalog.
- [ ] Add or update tests under `tests/llm_interactor` for `ollama-provider` runtime invocation, streaming, provider rows, catalog filtering, health, and actions.
- [ ] Add or update proxy tests proving chat and streaming work through provider runtime.
- [ ] Add or update proxy tests proving native tools, thinking/reasoning content, vision payloads, and trace fields remain stable.
- [ ] Add or update passthrough tests for `/api/tags`, `/api/show`, `/api/generate`, and `/api/chat`.
- [ ] Add or update `/v1/completions` tests proving legacy generate behavior remains stable.
- [ ] Add or update RAG tests proving embed and rerank calls use provider-backed adapters.
- [ ] Add or update indexing/ingestion tests proving embedding failures, retries, and batch behavior remain stable.
- [ ] Add or update WebUI tests proving model selectors, provider catalog, health/status cards, and the Ollama tab still load.
- [ ] Add or update ServiceStarter/extension-boundary tests proving app-level service actions use extension actions and `host_context.docker_runtime`.
- [ ] Add regression searches proving no new direct Ollama dependencies outside allowed temporary files.
- [ ] Run focused tests first, then broader `pytest` suites touched by the migration.

## Suggested Regression Searches

- [ ] Run `rg -n "from infrastructure\\.ollama|import infrastructure\\.ollama" api application CoreModules infrastructure extensions tests -g "*.py"` and verify every match is allowed or scheduled for removal.
- [ ] Run `rg -n "OllamaChatClient|OllamaEmbeddingProvider|OllamaRerankClient|OllamaEmbedAdapter" api application CoreModules infrastructure extensions tests -g "*.py"` and verify every match is allowed or scheduled for removal.
- [ ] Run `rg -n "OLLAMA_|/api/(tags|show|generate|chat|embed)|11434" api application CoreModules infrastructure extensions config tests -g "*.py" -g "*.yaml" -g "*.yml" -g "*.json"` and verify every match is provider-owned, compatibility-owned, config-owned, or test-owned.
- [ ] Run `rg -n "docker|Docker" extensions/bundled/ollama-provider -g "*.py"` and verify any service logic uses only `host_context.docker_runtime` plus `DockerContainerSpec`.
- [ ] Run `rg -n "ollama-provider|provider_catalog|LLMRuntime|RuntimeBackedChatClient" api CoreModules tests -g "*.py"` and verify new call sites use provider/runtime abstractions rather than direct Ollama clients.

## Acceptance Criteria

- [ ] `OLLAMA_EXTENSION_MIGRATION_TODO.md` exists at the repository root.
- [ ] The document is English-only.
- [ ] Every actionable item uses Markdown checkbox format `- [ ]`.
- [ ] The document explains what to migrate, when to migrate it, why it belongs in the extension, and how to validate each phase.
- [ ] The document identifies `ollama-provider` as the canonical owner of Ollama provider behavior.
- [ ] The document preserves current public compatibility expectations.
- [ ] The document includes migration guardrails for CoreUI, Docker, RAG ownership, config compatibility, and raw `/api/*` compatibility.
- [ ] The document includes test scenarios and regression searches.
- [ ] The document includes working criteria, phase completion criteria, and manual smoke checks.
- [ ] The document is usable by Codex and Cursor without needing extra implementation decisions.

## Assumptions

- [ ] This document is a roadmap and TODO guide, not the migration implementation itself.
- [ ] Scope is the full Ollama migration, not only the first wave.
- [ ] Existing public API compatibility is more important than deleting legacy code quickly.
- [ ] `ollama-provider` remains bundled and trusted during this migration.
- [ ] Core may keep temporary compatibility adapters while public routes are migrated behind provider-owned behavior.
- [ ] ServiceStarter can remain as a host-level capability, but app-level Ollama UX belongs to `ollama-provider`.
