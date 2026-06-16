# ChironAI — Layered Architecture

## Overview

The codebase is organized in layers: **Presentation → Application → Domain → Infrastructure**, with **Config** and **Utils** as cross-cutting concerns.

**Target layout:** The repository is moving to a **root-clean modular structure**: host-owned runtime code lives under `Core/`, reusable support modules live under `CoreModules/`, extension payloads live under `extensions/`, and the repository root stays free of unowned startup-critical packages. See [MODULAR_STRUCTURE.md](MODULAR_STRUCTURE.md) for the full target architecture.

**Current (legacy) layout:**

The paths below describe the current physical layout. Host layers and
host-owned services live under `Core/` and `Core/modules/`; reusable modules
remain under `CoreModules/`.

```
Core/api/            — Presentation (HTTP routes, CLI entrypoints)
Core/application/    — Application (use cases, container/wiring)
Core/domain/         — Domain (entities, services, ports, errors)
Core/infrastructure/ — Infrastructure (Qdrant, FS, crawl, logging)
Core/config/         — Configuration (YAML + env)
Core/core/           — Shared contracts/config package; import name `core`
tests/               — Pytest (domain, application, api, infrastructure)

Core/modules/        — Host-owned services (webui_backend, extensions_backend, crawler_service, …)
CoreModules/         — Shared core apps/libs (e.g. LlmProxy, RagService / `rag_service` + `chironai_rag`, CoreUI, MdIngestionService / `md_ingestion_service`)
```

## Data flow

- **HTTP**: Client -> `Core/api/http/rag_routes.py` (Flask; import name `api.http.rag_routes`) -> `rag_service.application.use_cases` -> `rag_service.domain.services/*` + ports -> `rag_service.infrastructure/*` (plus `Core/infrastructure/*` where the host still wires Qdrant and other shared adapters).
- **CLI**: `api/cli/crawl_cli.py` (or `python -m api.cli crawl`) -> delegates to crawler_service/webui_backend crawl/index workflows.
- **RAG**: `query_for_retrieval` (domain) → embed (Ollama) → search (Qdrant) → rerank (Ollama) → `build_context_block` (domain) → chat (Ollama).

## Layers

- **Core/api/**: Flask app (`create_app` in `Core/api/http/rag_routes.py`), CLI wrappers (`Core/api/cli/crawl_cli.py`). No direct infrastructure imports; uses application use cases.
- **application/**: Monolith-boundary helpers under `application/rag/` (for example `proxy_settings_contract`, `collection_freshness`). Canonical RAG use cases and composition live in **`rag_service.application`**; default RAG wiring is in **`rag_service.infrastructure.container`**.
- **domain/**: Shared non-RAG services (for example `markdown_meta`), ports, and errors. RAG entities and services are owned by **`rag_service.domain`**.
- **infrastructure/**: Qdrant compatibility shims, FS (MarkdownStore), crawl (Playwright), logging (WebUI error logger), metrics, and stack health. Ollama provider behavior is owned by the extension/runtime boundary; wire-format compatibility helpers live in `rag_service.infrastructure.openai_*` and LlmProxy modules.

## Running tests

From project root:

```bash
pip install -r requirements-dev.txt
pytest tests/
```

Configuration lives in **`pyproject.toml`** (`[tool.pytest.ini_options]`), including `pythonpath` entries for `CoreModules/RagService`, `CoreModules/MdIngestionService`, and `Core/modules/crawler_service`.

Coverage report for domain and application:

```bash
pytest tests/ --cov=domain --cov=application --cov-report=term-missing
```

Domain and application tests use mocks; API tests use Flask test client with wired use cases.

## Python packaging (monorepo)

The repository root is an installable project **`chironai`** ([`pyproject.toml`](../pyproject.toml)):

- **Editable install**: `pip install -e ".[dev]"` installs host packages from `Core/` (`application`, `api`, `config`, `core`, `domain`, `infrastructure`) and console scripts `tmrag` / `chironai`.
- **`Core/modules/*`**: host-owned service subtrees (each may ship its own README / layout). They are on `sys.path` for tests via pytest `pythonpath`, not necessarily part of the `chironai` distribution—add them to setuptools `packages.find` only if you want a single wheel to include everything.
- **`CoreModules/OllamaInteractor`**: separate distribution `ollama-interactor`; temporary compatibility adapters and the `ollama-provider` extension HTTP helper may invoke it for Ollama REST calls. The canonical extension source is its dedicated GitHub repository; `extensions/bundled/ollama-provider` is only a bootstrap/offline mirror.
- **`CoreModules/DockerManager`**: separate distribution `docker-manager`; provides Docker host capabilities to service-owning extensions and runtime helpers. App-level Ollama start/stop/status UX belongs to the `ollama-provider` extension, which receives Docker access through `host_context.docker_runtime`.
- **`CoreModules/LlmProxy`**: separate distribution `llm-proxy`; OpenAI-compatible `/v1` HTTP surface plus **Anthropic-compatible** `POST /v1/messages` and multiplexed `GET /v1/models` (via `anthropic-version` header), sharing the same RAG pipeline as `chat/completions`; also apply-edit and external-docs ingest. The host app supplies a `LlmProxyWiring` built in [`Core/api/http/llm_proxy_wiring.py`](../Core/api/http/llm_proxy_wiring.py); see [`CoreModules/LlmProxy/README.md`](../CoreModules/LlmProxy/README.md).
- **`CoreModules/WebInteraction`**: separate distribution `web-interaction`; free web snippet helpers (DuckDuckGo search, trigger heuristics) used when building the proxy system prompt. Wired from [`Core/api/http/llm_proxy_wiring.py`](../Core/api/http/llm_proxy_wiring.py); see [`CoreModules/WebInteraction/README.md`](../CoreModules/WebInteraction/README.md).
- **Import boundaries**: [import-linter](https://github.com/seddonym/import-linter) contract `domain_is_inner_layer` forbids `domain` → `application` | `api` | `infrastructure`. Run `lint-imports` after `pip install -r requirements-dev.txt`.

## Adding a new source or model

- **New provider model**: configure provider settings through the provider catalog and extension-owned UI/actions. Ollama-specific service and raw API behavior belongs to `ollama-provider`.
- **Temporary compatibility adapters**: root `infrastructure/ollama/*` adapter files and main-proxy raw Ollama routes have been removed. Public `/v1` compatibility now lives in `llm_proxy/ollama_compat.py`, `llm_proxy/wire_format/*`, and `rag_service.infrastructure.openai_*`. New app code should not add direct Ollama HTTP paths.
- **New crawl source**: add source configuration under the crawler config/source loader used by `crawler_service`; crawl CLI and index flow use it. For a new crawler implementation, implement `CrawlRunner` in `infrastructure/crawl/` and wire it in the application layer.
- **New vector store**: implement `RagRepository` under `rag_service.infrastructure` and wire it in `rag_service.infrastructure.container` instead of `QdrantRagRepository`.

## Service Control Boundary

Service orchestration for WebUI endpoints is routed through
`Core/api/http/service_control.py`.

- `Core/api/http/webui_routes.py` stays focused on HTTP composition.
- `Core/api/http/service_control.py` owns the WebUI bridge for Qdrant start/stop
  and delegates container lifecycle to `rag_service.runtime.RagRuntime`.
- Extension-owned service actions such as Ollama and Open WebUI use
  DockerManager through `host_context.docker_runtime`.

This keeps lifecycle logic out of large route modules and makes service
behavior easier to test and evolve.

## OpenAI Compatibility Policy

`CoreModules/LlmProxy` intentionally supports provider-backed OpenAI/Anthropic
chat compatibility. Raw Ollama-compatible routes and legacy `/v1/completions`
are not part of the core proxy surface.

- The canonical path remains `/v1/chat/completions`.
- `/v1/messages` and `/v1/responses` normalize to the same provider-backed chat pipeline.
