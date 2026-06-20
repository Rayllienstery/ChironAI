# Changelog

All notable changes to this project will be documented in this file.

## [0.7.37] - 2026-06-20
### Added
- Added advisory Bandit SAST with a documented baseline, gitleaks CI secret scanning, Dependabot configuration, and Flask security headers.

## [0.7.36] - 2026-06-20
### Added
- Added a CoreUI coverage gate with a 70% line threshold to the full quality gate.

## [0.7.35] - 2026-06-20
### Added
- Added CoreUI component tests for previously uncovered tabs and shared tab controls.

## [0.7.34] - 2026-06-20
### Changed
- Added shared Core contracts for Docker runtime, LLM runtime, and ChironAI errors while preserving existing module import facades.
- Added an import-linter boundary to prevent CoreModules from importing RAG, LlmProxy, or WebUIBackend implementations directly.

## [0.7.33] - 2026-06-19
### Changed
- Expanded `docs/ARCHITECTURE.md` to 313 lines with full layer rules, data flow diagrams, module responsibilities, high-risk zones, observability, and security posture.

## [0.7.32] - 2026-06-19
### Changed
- Added Linux full quality gate, Python version matrix (3.10–3.13), pip caching, and Codecov upload in CI.
- Coverage step now emits an XML report for Codecov.

## [0.7.31] - 2026-06-19
### Added
- Integration test for the full RAG pipeline using in-memory ports.

## [0.7.30] - 2026-06-19
### Added
- Property-based tests for the markdown meta block parser using Hypothesis.
### Changed
- Classified `.hypothesis` cache directory in the root layout guard.

## [0.7.29] - 2026-06-19
### Changed
- Split RAG test routes and OpenAI-compatible v1 blueprint into focused modules.

## [0.7.28] - 2026-06-19
### Changed
- Split LlmProxy chat completions handler and tool helpers into focused modules.

## [0.7.27] - 2026-06-19
### Changed
- Split Apple docs extraction into focused modules.
- Kept CoreUI lint focused on JavaScript sources while TypeScript remains covered by typecheck.

## [0.7.26] - 2026-06-19
### Changed
- Added required domain/application coverage gate.

## [0.7.25] - 2026-06-19
### Changed
- Made oversized-file auditing a required full quality gate step.

## [0.7.24] - 2026-06-19
### Changed
- Updated the generated API document to OpenAPI 3.1 and added schema validation to the quality gate.

## [0.7.23] - 2026-06-19
### Changed
- Added repository code ownership and pull request checklist templates.

## [0.7.22] - 2026-06-19
### Changed
- Added automated project version and changelog synchronization.

## [0.7.21] - 2026-06-18
### Added
- Added CoreUI OpenAPI TypeScript type generation from the backend OpenAPI spec.

## [0.7.20] - 2026-06-18
### Changed
- Made strict API drift checking a required minimal quality gate step.

## [0.7.19] - 2026-06-18
### Changed
- Enabled strict Pyright checks for core and domain code.
- Added typed defaults and Pyright paths for strict domain/core analysis.

## [0.7.18] - 2026-06-18
### Changed
- Enabled Ruff SIM rules and simplified existing Python code to satisfy them.

## [0.7.17] - 2026-06-18
### Changed
- Expanded import-linter layer contracts for application and infrastructure boundaries.
- Moved stack health provider checks out of the infrastructure layer.

## [0.7.16] - 2026-06-18
### Added
- Added local pre-commit hooks for Ruff, CoreUI formatting, version drift, and lockfile checks.

## [0.7.15] - 2026-06-18
### Added
- Added an automated version drift check to keep package, runtime, and changelog versions aligned.
- Removed stale CoreUI extension-runtime exports that blocked the minimal quality gate.

## [0.7.14] - 2026-06-18
### Fixed
- Synchronized the root package version with the canonical core version.

## [0.7.13] - 2026-06-17
### Fixed
- Stopped appending output-budget error text to chat responses when finish_reason is already length, avoiding duplicate output-limit warnings in Cursor/Kilo clients.

## [0.7.12] - 2026-06-17
### Fixed
- Streamed upstream Ollama chat failures now use the same clear proxy error format as non-stream paths.
- Ollama chat HTTP calls retry transient 503/502/504 responses after RAG rerank or other short-lived upstream load.

## [0.7.11] - 2026-06-17
### Fixed
- Prevented stale lazy-module prefetches from blocking later tab navigation imports.

## [0.7.10] - 2026-06-17
### Fixed
- Made the Extensions tab render installed extensions without waiting for slower provider/UI payload requests.

## [0.7.9] - 2026-06-17
### Changed
- Notification center opens at the latest items and shows a Latest jump button when scrolled up.

## [0.7.8] - 2026-06-17
### Fixed
- Notification center scrolls as one vertical list with a hidden scrollbar instead of per-card scrolling.

## [0.7.7] - 2026-06-17
### Changed
- Removed legacy compatibility shims (`config.rag_prompts`, `rag_repository_impl`) and dead one-off split scripts.
- Migrated application code to `get_default_*` config getters with guardrails and centralized `proxy_settings` loading.
- Replaced RAG trace cross-tab `CustomEvent` bridge with sessionStorage-only mirror flow.
- Delegated external-docs Qdrant search to canonical `QdrantRagRepository`.
- Documented intentional `/v1` wire-format and legacy tool-stream compatibility boundaries.
- Fixed WebUI backend `project_root()` and startup path bootstrap so `build_and_run` serves CoreUI and loads extensions.

## [0.7.6] - 2026-06-16
### Changed
- Moved host runtime packages under `Core/` while preserving public import names.
- Updated tooling, startup paths, and architecture docs for the new host container.

## [0.7.5] - 2026-06-16
### Added
- Added a root layout guardrail for classified top-level repository ownership.
- Documented current root folder ownership in project architecture rules.

## [0.7.4] - 2026-06-16
### Fixed
- Restored Qdrant collection list/delete HTTP calls in WebUI RAG routes.
- Fixed create-collection embedding runtime syntax so Python gates and test collection pass again.

## [0.7.3] - 2026-06-15
### Added
- HTTP test splits: `test_http_chat_completions.py`, `test_http_v1_models.py`, `test_http_extensions.py`.
- CoreUI service modules `extensions.js` and `rag.js` (re-exported from `api.js`).
- Crawler source filesystem helpers in `webui_crawler_helpers.py` (`load_source_meta`, `discover_crawler_sources`).

### Changed
- `test_http_endpoints.py` monolith reduced to rag-trigger smoke; chat/v1 models moved to domain suites.
- `test_extensions_routes.py` is a thin re-export of `test_http_extensions.py`.
- API drift-check normalizes `${...}` template segments in frontend paths to `{param}`.
- `api.js` further split (~1143 → ~610 lines).

## [0.7.2] - 2026-06-15
### Added
- HTTP test splits: `test_http_observability.py`, `test_http_llm_proxy_builds.py`.
- CoreUI service modules `proxy.js` and `crawler.js` (re-exported from `api.js`).
- Pseudo-locale `en-XA` in Localization catalog; nav labels wired via `t()` in App.
- Linux CI job (`linux-fast`: ruff + `pytest -m fast`).
- RagTab RTL smoke test.

### Changed
- `hybrid_sparse.py` and `retrieval_ui_overrides.py` use `settings_resolver` / `proxy_settings_contract`.
- API drift-check and CoreUI `npm run test` are **required** in `full` quality gate.
- `webui_routes.py` and `llm_proxy_wiring.py` use `ensure_webui_composition_paths` instead of raw `sys.path.insert`.
- Ruff extended with `B` (bugbear) rules; targeted ignores for legacy patterns.
- ESLint errors fixed in legacy tabs (conditional hooks, empty catch blocks).

## [0.7.1] - 2026-06-15
### Added
- Way to 1000 Phase 0–6 foundations: quality gates, settings resolver, CoreUI lint/test harness, test splits, Docker scaffold, and shared Localization catalog.
- `.editorconfig`, oversized-file audit, API drift-check script, and documented gate profiles.
- CoreUI ESLint, Prettier, Vitest, TypeScript check on services, and `http.js` service split start.
- `CoreModules/Localization` with Python `t()` and CoreUI i18n adapter skeleton.

### Changed
- Split HTTP health and proxy-auth tests from `test_http_endpoints.py`; shared fixtures in `tests/api/http_fixtures.py`.
- WebUI backend entrypoint uses conditional import-path bootstrap instead of unconditional `sys.path.insert`.

## [0.7.0] - 2026-06-14
### Changed
- Promoted the application version to 0.7.0.

## [0.6.87] - 2026-06-14
### Changed
- Improved Swagger/OpenAPI operation descriptions and structured schemas for key WebUI developer endpoints.

## [0.6.86] - 2026-06-14
### Added
- Added OpenAPI and Swagger UI endpoints with a CoreUI Developer Tools Swagger tab.
- Required API documentation updates in the project rules for endpoint changes.

## [0.6.85] - 2026-06-14
### Changed
- Made pytest disable extension background bootstrap by default so quality gates do not hang after successful test summaries.

## [0.6.84] - 2026-06-14
### Changed
- Added product hardening smoke coverage for critical WebUI flows and required exact backend confirmation for destructive Docker delete actions.

## [0.6.83] - 2026-06-14
### Changed
- Added a reusable quality gate runner with explicit minimal, full, and release profiles, plus a CI workflow that runs the minimal gate.
- Made the dependency update job test hermetic so full quality gates no longer mutate CoreUI lockfiles.

## [0.6.82] - 2026-06-14
### Changed
- Tightened CoreUI dependency hygiene by switching local install scripts to lockfile-first npm installs and adding a lockfile drift check for frontend builds.

## [0.6.81] - 2026-06-14
### Changed
- Added WebUI API contract guards that keep the CoreUI API base, Flask WebUI blueprints, and `/version` response shape synchronized with `core.contracts.webui_api`.

## [0.6.80] - 2026-06-14
### Changed
- Extracted the crawler create-collection progress UI into a shared CoreUI component used by both the Crawler tab and crawler modals, removing duplicated progress rendering logic.

## [0.6.79] - 2026-06-14
### Changed
- Split crawler indexing/logging helpers and RAG test authoring helpers out of large backend route modules, with focused tests for the extracted behavior.

## [0.6.78] - 2026-06-14
### Changed
- Added pytest test group markers for fast, slow, API, domain, service, extension, and integration workflows, and isolated the long-running dependency job test from the local fast gate.

### Fixed
- Updated RAG and Ollama provider tests to match the current retrieval scoring and HTTP-backed provider behavior.

## [0.6.77] - 2026-06-14
### Changed
- Cleaned up tooling baseline checks by removing stale `utils` paths, enabling Ruff pyflakes checks, clearing the CoreUI module timing unused export, and fixing newly surfaced lint issues.

## [0.6.76] - 2026-06-14
### Fixed
- Removed the divider line above the LLM Proxy build wizard footer buttons.

## [0.6.75] - 2026-06-14
### Fixed
- Corrected the LLM Proxy build wizard footer so Back stays left, Save build stays centered, and Next stays right.

## [0.6.74] - 2026-06-14
### Fixed
- Expanded `/v1/models` vision/tool capability aliases and added single-model retrieval so Kilo/Roo/Cline-style clients keep image attachments enabled for proxy models.

## [0.6.73] - 2026-06-13
### Fixed
- Refreshed Ollama extension model lists after pull/delete/refresh actions and made the runtime tab fetch a fresh model list when opened.

## [0.6.72] - 2026-06-13
### Fixed
- Prevented extension tab payload timeouts from rendering as a final unavailable page; timed-out payload refreshes now stay retryable and keep the loading diagnostics active.

## [0.6.71] - 2026-06-11
### Changed
- Optimized Extensions tab loading with manifest-first tab rendering, background tab payload refresh, cached/stale payload states, and CoreUI loading diagnostics for descriptor and payload phases.

## [0.6.70] - 2026-06-11
### Added
- Added a detailed CoreUI extension runtime loading view that shows loaded, active, pending, and blocked stages, with a CoreUI Showcase example.

## [0.6.69] - 2026-06-11
### Fixed
- Prevented extension tab UI hooks from blocking WebUI requests indefinitely and stopped extension runtime errors from immediately restarting the loading state.

## [0.6.68] - 2026-06-11
### Fixed
- Corrected WebUI startup diagnostics so React mount timing is captured once at first render and completed lazy module imports do not reappear as stuck in-progress loads.

## [0.6.67] - 2026-06-11
### Fixed
- Wrapped upstream Ollama chat failures with a clearer proxy error message that includes status, URL, model, and over-budget context hints.

## [0.6.66] - 2026-06-10
### Fixed
- Sandboxed extensions can now call `docker_runtime.check_image_update`, fixing the Docker card `Check image version` action.

## [0.6.65] - 2026-06-10
### Changed
- Open WebUI extension now renders its runtime card through the standardized `CoreUIDockerCard` component (read-only demo mode stays available for the showcase). The card supports editable backend URL with autosave, per-action busy state with elapsed timer chips, confirm dialogs, and tone-aware `Status` / `Image version` meta tiles.
- `CoreUIDockerCard` upgraded with a live mode (new `service`, `busyActionId`, `activeAction`, `actionTimerNow`, `fieldKey` props) and a new `check_image_version` action on the open-webui provider that calls `docker_runtime.check_image_update` and caches the result on the provider.

## [0.6.64] - 2026-06-10
### Added
- Standardized `CoreUIDockerCard` component (header with name, description, status badge, optional HTTP code; two-column body with backend URL field, action row, and metadata tiles). Registered in CoreUI Showcase → Cards → Runtime cards with the Open WebUI runtime data and a stopped-state variant.
- Added `Status` and `Image version` metadata tiles to the Docker card with tone-aware badges (success/warning/error for running/up-to-date/stopped/update-available/etc.).

## [0.6.63] - 2026-06-09
### Changed
- Streaming dependency jobs now report the current step (ecosystem, phase, package) in real time through both the Dependencies tab and a live notification card, and surface the full updated package list (with old → new versions when known) in the completion notification.

## [0.6.62] - 2026-06-08
### Fixed
- Make the notification center leave animation actually play. The data layer is now updated only after the CSS exit animation finishes, and dismissed/leaving cards stay in the DOM until their animation completes.

## [0.6.61] - 2026-06-08
### Changed
- Added a reverse left-to-right exit animation to notification center cards and the Clear capsule, mirroring the right-to-left enter animation.

## [0.6.60] - 2026-06-08
### Changed
- Added a stale-prefetch guard for lazy CoreUI module timings so background imports cannot remain as active loading rows forever.
- Added a module timing regression test that verifies stale prefetches do not break later tab navigation.

## [0.6.59] - 2026-06-08
### Fixed
- Prevented idle-prefetch timeouts from surfacing as tab navigation errors for lazy CoreUI modules.

## [0.6.58] - 2026-06-08
### Changed
- Added live lazy module loading diagnostics to the Performance tab, including active loads, elapsed time, current step, and source.
- Prefetched tab and nested testing/logs chunks during browser idle time to reduce visible tab loading delays.

## [0.6.57] - 2026-06-08
### Changed
- Extracted the floating notification center action buttons into a shared `CoreUINotificationActionButton` component, used by both the Bell toggle and the Clear action in `NotificationCenterShell`, and showcased in the CoreUI Showcase Buttons subtab (reused inside the Notifications subtab).

## [0.6.56] - 2026-06-08
### Changed
- Replaced the SVG broom icon in the notification center Clear capsule with a Material Symbol (`cleaning_services`), added a "Clear" label, and aligned the capsule height with the Bell button.

## [0.6.55] - 2026-06-08
### Added
- Added a `Notifications` subtab to the CoreUI Showcase with notification card variants, bell/clear buttons, history popover, and module label previews.

## [0.6.54] - 2026-06-08
### Changed
- Reverted the standalone `Tab Selector` subtab and placed `CoreUIPillTabs` and `CoreUISubtabs` back inside `Layout & Navigation` as a dedicated `Tab Selector` section at the end.

## [0.6.53] - 2026-06-08
### Changed
- Moved `CoreUIPillTabs` and `CoreUISubtabs` out of the Core Components subtab into a new dedicated `Tab Selector` subtab.

## [0.6.52] - 2026-06-08
### Added
- Added a `Cards` subtab to the CoreUI Showcase with a labeled card anatomy (header, body, footer) and moved card, main card patterns, and model card variants into it.
- Split the `Colors` subtab into internal sections (Fonts first, then Colors, then Layout foundations) for clearer navigation.

## [0.6.51] - 2026-06-08
### Fixed
- Stopped suppressing client-provided native tools based on Ollama model capability metadata.

## [0.6.50] - 2026-06-08
### Fixed
- Preserved native tool calls for vision requests when the final Ollama model supports both tools and image input.

## [0.6.49] - 2026-06-08
### Changed
- Documented the CoreUI tab/subtab component rule for pill tabs outside cards and subtabs inside cards.

## [0.6.48] - 2026-06-08
### Changed
- Expanded regression coverage for OpenCode vision routing, Ollama capability lookup, multipart image normalization, and prior error-artifact filtering.

## [0.6.47] - 2026-06-08
### Fixed
- Prevented prior proxy transport-error artifacts from being forwarded back into OpenCode conversation history.

## [0.6.46] - 2026-06-08
### Added
- Introduced `CoreModules/LogsManager` for internal read-only access to RAG Fusion proxy journal logs in `logs/webui.db`.

## [0.6.45] - 2026-06-08
### Fixed
- Made Ollama vision fallback use the configured chat URL when provider-runtime adapters do not expose an upstream `_url`.

## [0.6.44] - 2026-06-08
### Fixed
- Added Ollama `/api/tags` capability detection and routed image requests to a vision-capable fallback when the selected build model is text-only.

## [0.6.43] - 2026-06-08
### Fixed
- Avoided Ollama 400 errors for streamed vision requests from OpenCode by suppressing native tools when images are present.

## [0.6.42] - 2026-06-08
### Fixed
- Marked LLM Proxy build models as image-capable for OpenCode-compatible clients and normalized AI SDK image file parts.

## [0.6.41] - 2026-06-07
### Changed
- Made `modules/webui_backend` the canonical `webui_backend` package and removed the duplicate CoreModules package namespace.

## [0.6.40] - 2026-06-07
### Changed
- Added a Docker event stream and made CoreUI service status refresh react to container/image events with slower fallback polling.

## [0.6.39] - 2026-06-07
### Fixed
- Optimized Docker image update checks to avoid extra remote metadata lookups when the local digest is already current.

## [0.6.38] - 2026-06-07
### Fixed
- Made the installed Extensions list avoid blocking on Docker image version checks during initial load.

## [0.6.37] - 2026-06-07
### Fixed
- Cleaned up the Ollama extension Docker section so it shows container status and avoids empty or unknown version fields.

## [0.6.36] - 2026-06-07
### Fixed
- Removed crawled web-page markdown outputs from the repository and ignored the testing crawl output directory.

## [0.6.35] - 2026-06-07
### Fixed
- Made the Extensions tab stop blocking Installed and Providers on the remote registry load.

## [0.6.34] - 2026-06-07
### Changed
- Made WebUI startup and the initial CoreUI render stop blocking on provider bootstrap, session creation, delayed shell requests, or startup-critical lazy chunks so Dashboard, Performance, and WebUI pages can open immediately.

## [0.6.33] - 2026-06-06
### Changed
- Removed core create-collection direct Ollama embedding ownership and made CoreUI provider-facing text provider-neutral.

## [0.6.32] - 2026-06-06
### Changed
- Reworked Extensions tab cards into a single-column horizontal layout with clearer metadata chips and action placement.

## [0.6.31] - 2026-06-05
### Changed
- Enabled real parallel embedding workers for create-collection indexing and raised the default worker count to four.

## [0.6.30] - 2026-06-05
### Changed
- Increased create-collection progress polling to three updates per second, switched durations to H:MM:SS, and reduced live status payload size.

## [0.6.29] - 2026-06-05
### Changed
- Expanded create-collection recent activity to eight rows and included skipped/error files alongside embedding rows.

## [0.6.28] - 2026-06-04
### Fixed
- Restored live create-collection page and chunk counts while embedding batches are queued.

## [0.6.27] - 2026-06-04
### Changed
- Added create-collection timing telemetry to progress UI, notifications, and final reports.

## [0.6.26] - 2026-06-04
### Changed
- Restored faster create-collection embedding throughput with larger adaptive batches.

## [0.6.25] - 2026-06-03
### Changed
- Combined create-collection indexed and total page progress into one leading metric card.

## [0.6.24] - 2026-06-03
### Changed
- Added embedding-vector progress history with per-file chars/chunks and Material-style motion.

## [0.6.23] - 2026-06-03
### Changed
- Added a CoreUI Dependencies tab with dependency inventory, update checks, update jobs, and Notification Center events.

## [0.6.22] - 2026-06-03
### Changed
- Added installed-extension enable/disable/remove actions and immediate sidebar refresh after extension lifecycle changes.

## [0.6.21] - 2026-06-03
### Changed
- Added a live create-collection notification action that reopens the indexing details modal.

## [0.6.20] - 2026-06-03
### Changed
- Added safer batched embedding input clipping and context-length fallback during collection indexing.

## [0.6.19] - 2026-06-02
### Changed
- Tightened Apple collection ingestion cleanup for community boilerplate, low-value conformity chunks, deduplication, chunk overlap, and source metadata.

## [0.6.18] - 2026-06-02
### Changed
- Made the create-collection recent issues panel expand into the remaining modal height.

## [0.6.17] - 2026-06-02
### Changed
- Made the root build script install CoreUI npm dependencies before building when Vite is missing.
- Removed the unused CoreUI icon package left after Ollama-specific UI cleanup.

## [0.6.16] - 2026-06-02
### Changed
- Added full create-collection indexing issue details and counters to final structured logs and notification metadata.

## [0.6.15] - 2026-06-02
### Changed
- Expanded the create-collection progress modal and made recent indexing issues easier to scan with separated log rows.

## [0.6.14] - 2026-06-01
### Changed
- Added elapsed/duration timers to generic extension runtime actions and their CoreUI notifications.

## [0.6.13] - 2026-06-01
### Removed
- Removed core raw Ollama-compatible routes, legacy `/v1/completions`, direct Ollama embed fallback paths, and CoreUI Ollama-specific pull/service UI ownership.

## [0.6.12] - 2026-06-01
### Changed
- Removed fresh static-analysis dead-code tails from WebUI routes and focused tests, and removed the empty untracked `scripts/bin` directory.

## [0.6.11] - 2026-06-01
### Changed
- Added JSDoc to all CoreUI components: Card, Badge, Slider, PillTabs, Subtabs, Modal, Button, EmptyState, Sparkline, StandByScreen, all tab roots, and all notification bridges.
- Standardized Python docstrings in `domain/ports/` (embedding, rag_repository, chat_llm, markdown_store, crawl, rerank_client) and `infrastructure/database/*` repositories to Google Style with Args/Returns/Raises.
- Cleaned up `# noqa` comments to specify the exact linting rule.

## [0.6.10] - 2026-06-01
### Changed
- Standardized Python docstrings to Google Style across core packages.
- Added JSDoc documentation to key CoreUI components.
- Improved configuration documentation with explanatory comments in YAML files.
- Added deprecation rationale and migration plans for legacy shims.
- Cleaned up code comments and standardized `# noqa` rules.
- Added module-level documentation to utility scripts.
- Removed obsolete `prompts/.trash/` directory.

## [0.6.9] - 2026-06-01
### Changed
- Added file-aware recent indexing issues and prepare character statistics to the create-collection progress UI.

## [0.6.8] - 2026-06-01
### Changed
- Refined the Crawler / Indexer live notification layout for collection indexing so progress details stay compact and readable inside the notification center.

## [0.6.7] - 2026-05-31
### Removed
- Removed Qdrant unnamed-vector collections, `QDRANT_LEGACY_DENSE_FALLBACK_ENABLED`, and direct `/api/tags` health fallback when the Ollama provider runtime is unavailable.

### Added
- Added a repo-wide quality audit roadmap for staged cleanup, documentation sync, and guardrail work.

### Changed
- Synced architecture docs (`docs/ARCHITECTURE.md`, `docs/legacy_map.md`, `Improvements2.md`, `Improvement.md`) with canonical `rag_service.*` ownership after root RAG shim removal.
- Documented live `scripts/*` inventory in `DEPENDENCIES.md`.
- Removed stale `test_compat_wrappers.py` entry from Ollama migration import guardrails.
- Extracted WebUI model settings and Model Tester routes into `api/http/webui_model_tester_routes.py`.
- Extracted WebUI RAG model settings, pipeline diagram, and Qdrant lifecycle routes into `api/http/webui_rag_routes.py`.
- Extracted WebUI chat/model list routes into `api/http/webui_chat_routes.py`.
- Extracted shared provider/runtime helpers into `api/http/webui_provider_helpers.py`; slimmed `webui_routes.py` to a composition root.
- Extracted external-docs testing preview into `api/http/webui_testing_routes.py`; deduped `webui_llm_proxy_routes` / `webui_crawler_routes` imports.
- Moved pure `/v1/chat/completions` request parsers into `llm_proxy/chat_completions_request_parsing.py` with dedicated tests.
- Moved response/message-shaping helpers into `llm_proxy/chat_completions_response_helpers.py` with dedicated tests.
- Moved handler-side pure helpers into `llm_proxy/chat_completions_handler_helpers.py` with dedicated tests.
- Extracted OpenAI SSE streaming helpers into `llm_proxy/chat_completions_streaming.py` with dedicated tests.
- Documented Qdrant vector modes; removed unnamed-vector collections and legacy dense search fallback (named `dense` + hybrid only).
- Documented CoreUI `api.js` ↔ `webui_*_routes` alignment (`CoreModules/CoreUI/docs/WEBUI_API.md`); verified `knip` and production build.
- Added `config/CONFIG_AUTHORITY.md` and `tests/config/test_config_precedence.py` documenting env-over-YAML precedence.
- Added `config/ENV_REFERENCE.md` and `infrastructure/ollama/README.md`; synced Ollama import guardrail allowlist and `docs/legacy_map.md`.
- Added `--help` to `scripts/audit_apple_ingest_filter.py` and CLI smoke tests under `tests/scripts/`.

## [0.6.6] - 2026-05-31
### Removed
- Removed the obsolete one-off SQLite log inspection script from `scripts`.

## [0.6.5] - 2026-05-31
### Changed
- Removed internal root RAG compatibility shims and moved callers to canonical `rag_service` imports.
- Cleaned static-analysis dead code across Python tests, backend imports, and CoreUI service docs.

## [0.6.4] - 2026-05-31
### Removed
- Removed the legacy ServiceStarter module, CLI, dev install entry, and tests.

### Changed
- Routed WebUI Qdrant start/stop through RagRuntime and DockerManager.
- Kept Docker service lifecycle ownership with service-specific extensions and DockerManager host capabilities.

## [0.6.3] - 2026-05-31
### Changed
- Replaced the CoreUI stand-by screen icon mark with an uncontained Material-style morphing loading indicator and removed the decorative ellipse behind it.

## [0.6.2] - 2026-05-31
### Changed
- Refined the CoreUI stand-by loading screen with a stronger Material 3 tonal layout, filled icon mark, thicker indeterminate progress indicator, and clearer module status row.

## [0.6.1] - 2026-05-31
### Changed
- Updated the CoreUI stand-by loading screen to show an indeterminate progress bar with the currently loading module name underneath.

## [0.6.0] - 2026-05-29
### Added
- Added **Performance tab** under Developer Tools — a new CoreUI module for runtime and startup diagnostics.
- Added `Startup` subtab with `CoreUIPipelinePreview` showing every instrumented server startup phase (Flask App Init, LLM Proxy Wiring, Blueprint Registration, Session Manager, Extensions Runtime).
- Clicking any pipeline phase opens a `CoreUIModal` with two subtabs: human-readable `Summary` (waterfall bars, sub-steps, metadata) and `Debug Log` (raw JSON + log lines for AI analysis).
- Browser Navigation Timing is posted on tab mount and merged into the startup report as a `WebUI (Browser)` phase.
- Added `api/http/startup_timing.py` — thread-safe in-memory phase registry modelled after `proxy_status.py`.
- Added `api/http/webui_performance_routes.py` — `GET /api/webui/performance/startup` and `POST /api/webui/performance/browser-timing`.
- Added `StartupStep`, `StartupPhase`, `StartupPerformanceResponse` TypedDicts to `core/contracts/webui_api.py`.
- Added `getStartupPerformance()` and `postBrowserTiming()` to `CoreModules/CoreUI/src/services/api.js`.
- Prevented purple FOUC on page load: theme is now saved to `localStorage` in `applyTheme()` and restored synchronously in `index.html` before React renders.
- Added non-blocking Google Fonts load (`media="print"`) and `<link rel="preconnect">` hints to eliminate render-blocking external requests.
- Added CSS loading spinner (`#root:empty::after`) shown while the JS bundle executes.

### Changed
- Instrumented `create_app()` in `rag_routes.py` with per-step startup timing (RAG params, LLM Proxy Wiring, blueprint registration).
- Instrumented `rag_proxy.py` to record Session Manager pre-warm timing.
- Instrumented `_bootstrap_runtime_body()` in `llm_interactor/manager.py` to record extension discovery and per-extension sandbox startup timing.

## [0.5.2] - 2026-05-29
### Changed
- Registry extension cards now receive GitHub-backed icon URLs before install.
- Remote registry SVG icons now render as images in CoreUI instead of local masks.

## [0.5.1] - 2026-05-28
### Added
- Added extension archive hardening for uncompressed-size bombs, excessive file counts, compression-ratio abuse, and symlink zip entries.
- Added extension asset symlink rejection and guardrails that prevent legacy extension Flask keys from returning.

### Changed
- Extension HTTP routes now return sanitized public error codes/messages while logging internal details server-side.
- Extension install tests and provenance paths now use trusted GitHub archive hosts.
- Removed the legacy `llm_extensions_service` Flask extension alias after the migration to contract accessors.

## [0.5.0] - 2026-05-28
### Added
- Added the extension-management service facade, registry-client module boundary, and API guardrails for the GitHub extensions migration release.

### Changed
- Routed extension API state through contract-shaped accessors instead of legacy Flask extension keys.
- Removed direct bundled-extension HTTP route discovery from API startup and replaced Ollama compatibility routes with contract-backed handlers.
- Extension lifecycle operations now attempt targeted runtime reloads and report reload status instead of requiring a full project reload in normal cases.
- Extension registry/details load failures now persist Notifications center entries.
- Marked the Extensions GitHub migration acceptance checklist complete for the `0.5.0` release.

## [0.4.40] - 2026-05-28
### Added
- Added high-risk extension capability-expansion consent checks for updates.
- Added remote emergency blocklist publishing and validation in the public extensions registry.

### Changed
- Extension blocklist loading now defaults to the GitHub-hosted blocklist with a local offline fallback cache.

## [0.4.39] - 2026-05-28
### Added
- Added emergency extension blocklist policy, offline blocklist cache configuration, and tests for blocked installs and startup disablement.

### Changed
- Extension registry and installed status now surface blocklist matches, and blocklisted installed extensions cannot be re-enabled.

## [0.4.38] - 2026-05-28
### Added
- Added bundled extension bootstrap-copy documentation, local registry fallback documentation, and a sync/check script for bundled extension payloads.

### Changed
- Clarified architecture docs so dedicated extension repositories are the source of truth and bundled copies are offline/bootstrap mirrors.

## [0.4.37] - 2026-05-28
### Added
- Added GitHub extension registry configuration with local fallback, repository-backed extension details, README/version loading, and CoreUI install details modal.
- Added Notifications center persistence for extension install, remove, enable, disable, restart, and kill actions.

### Changed
- Wired remote extension installs to resolve latest GitHub release artifacts and record release provenance.
- Preserved explicit GitHub branch/ref provenance while using safe on-disk folder names for refs that contain path separators.

## [0.4.36] - 2026-05-28
### Added
- Extracted the initial bundled extensions into dedicated GitHub repositories with validation CI, release tags, release archives, digests, dependency inventories, and provenance attestations.

### Changed
- Marked Phase 4 of the Extensions GitHub migration plan complete and documented the extracted extension repositories and release artifacts.

## [0.4.35] - 2026-05-27
### Changed
- Clarified Open WebUI extension wording so Docker runtime ownership remains with the DockerManager CoreModule and extensions only use host capabilities.

## [0.4.34] - 2026-05-27
### Added
- Created the public ChironAI Extensions Registry GitHub repository with initial registry entries, schema, validation script, CI, and contribution policy.

### Changed
- Marked Phase 3 of the Extensions GitHub migration plan complete.

## [0.4.33] - 2026-05-27
### Added
- Added Phase 2 registry diagnostics, GitHub repository metadata client support, install provenance fields, and hardening tests.

### Changed
- Hardened extension install activation with manifest compatibility checks, atomic staging, rollback preservation, security scan state, and targeted reload scope responses.

## [0.4.32] - 2026-05-27
### Added
- Added the Phase 1 Extensions contract lock and shared Extensions API DTO contract.

### Changed
- Marked Phase 1 of the Extensions GitHub migration plan complete.

## [0.4.31] - 2026-05-27
### Changed
- Marked the Extensions GitHub migration as targeting project release `0.5.0`.

## [0.4.30] - 2026-05-27
### Changed
- Expanded the Extensions GitHub migration plan with red-team failure modes and guardrails.

## [0.4.29] - 2026-05-27
### Changed
- Expanded the Extensions GitHub migration plan with extension-management module boundaries outside core.
- Updated the modular structure target with the Extensions backend and host boundary.

## [0.4.28] - 2026-05-27
### Changed
- Expanded the Extensions GitHub migration plan with targeted reload and fault isolation requirements.

## [0.4.27] - 2026-05-27
### Changed
- Named the target extension registry repository `ChironAI Extensions Registry`.

## [0.4.26] - 2026-05-27
### Changed
- Expanded the Extensions GitHub migration plan with marketplace and supply-chain research findings.

## [0.4.25] - 2026-05-27
### Changed
- Expanded the Extensions GitHub migration plan with provenance, atomic updates, README safety, permission previews, and removal ownership requirements.

## [0.4.24] - 2026-05-27
### Changed
- Expanded the Extensions GitHub migration plan with full install controls in the extension details header.

## [0.4.23] - 2026-05-27
### Changed
- Expanded the Extensions GitHub migration plan with README modals, repository-backed version selection, and update security enforcement.

## [0.4.22] - 2026-05-27
### Changed
- Expanded the Extensions GitHub migration plan with Notifications center lifecycle coverage.

## [0.4.21] - 2026-05-27
### Added
- Added the Extensions GitHub migration task plan and readiness checklist.

## [0.4.20] - 2026-05-27
### Changed
- Wrapped Architecture sub-tab content in a styled card with borders and shadows.

## [0.4.19] - 2026-05-27
### Changed
- Updated Dev Documentation to use `CoreUIPillTabs` for sub-tab navigation.
- Moved sub-tab selector below the header title and description.

## [0.4.18] - 2026-05-27
### Changed
- Moved "Architecture Overview" from Dashboard to a new "Architecture" sub-tab in Dev Documentation.
- Added sub-tabs to Dev Documentation: "Overview" (extension guide) and "Architecture".

## [0.4.17] - 2026-05-26
### Changed
- Unified the visual style of both tabs in the Proxy API Key modal using a card-based grid layout.
- Refactored "API Key" tab to use the same card components as the "How to use" tab.

## [0.4.16] - 2026-05-26
### Changed
- Redesigned "How to use" tab in Proxy API Key modal with a card-based layout.
- Integrated real proxy base URL from settings into the "How to use" instructions.

## [0.4.15] - 2026-05-26
### Changed
- Added sub-tabs to the Proxy API Key modal (API Key and How to use).
- Moved proxy usage instructions from the RAG Fusion Proxy tab into the modal.

## [0.4.14] - 2026-05-26
### Changed
- Moved proxy API key security controls into a dedicated Tokens and Security tab.

## [0.4.13] - 2026-05-26
### Fixed
- Proxy API key modal content now keeps scoped internal padding and full-width step rows.

## [0.4.12] - 2026-05-26
### Fixed
- LLM Proxy native tool turns no longer append system messages after tool results for Ollama.

## [0.4.11] - 2026-05-26
### Changed
- Proxy API key modal now presents a focused quick start for external client setup.

## [0.4.10] - 2026-05-26
### Fixed
- ChironAI Codex profiles now bypass the broken Codex v0.133 Windows sandbox setup path.

## [0.4.9] - 2026-05-26
### Fixed
- Responses SSE message events now initialize empty content before text deltas for Codex clients.

## [0.4.8] - 2026-05-26
### Fixed
- Codex build catalog entries now include model message templates for personality-aware launches.

## [0.4.7] - 2026-05-26
### Fixed
- Codex build catalog entries now include the full required metadata set for current Codex CLI.

## [0.4.6] - 2026-05-26
### Fixed
- Codex model catalog entries now include required reasoning metadata.

## [0.4.5] - 2026-05-23
### Added
- Codex launcher now generates ChironAI build metadata for IDE models.

## [0.4.4] - 2026-05-23
### Changed
- Notification changelog formatting: `###` headers replaced with accent-colored dot markers, lines separated properly.

## [0.4.3] - 2026-05-22
### Added
- Configurable WebUI/backend server port in Settings with restart-required status.

### Changed
- Startup scripts now resolve and open the configured WebUI port.

## [0.4.2] - 2026-05-22
### Added
- Welcome notification with version and changelog on WebUI startup.
- Centralized version management in `core/version.py`.

## [0.4.1] - 2026-05-22
### Changed
- Translated Russian comments and documentation to English for project uniformity.
- Updated `AI_RULES.md` with versioning and changelog requirements.

## [0.4.0] - 2026-05-22
### Added
- Project version bumped to 0.4.0.
- New priorities focused on Observability and Quality.
- Hybrid search (vector + keyword) fully integrated.
- Web supplement (DuckDuckGo/Wikipedia) integrated into the pipeline.
- RAG Tests framework with Markdown-based test cases and SQLite history.

## [0.3.0] - 2026-04-26
### Added
- Initial RAG pipeline with Qdrant and Ollama.
- Basic WebUI for interaction and configuration.
- Support for Apple documentation crawling and indexing.
- System prompt versioning.

## [0.2.0] - 2026-03-18
### Added
- Core domain models and hexagonal architecture setup.
- Basic CLI for indexing and querying.

## [0.1.0] - 2026-02-15
### Added
- Project initialization.
- Basic project structure and dependencies.
