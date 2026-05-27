# Changelog

All notable changes to this project will be documented in this file.

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
