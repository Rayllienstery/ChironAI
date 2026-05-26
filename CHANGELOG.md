# Changelog

All notable changes to this project will be documented in this file.

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
