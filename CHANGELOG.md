# Changelog

All notable changes to this project will be documented in this file.

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
