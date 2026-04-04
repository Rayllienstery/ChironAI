# ChironAI — Layered Architecture

## Overview

The codebase is organized in layers: **Presentation → Application → Domain → Infrastructure**, with **Config** and **Utils** as cross-cutting concerns.

**Target layout:** The repository is moving to a **modular structure**: each major domain (RAG, MD ingestion, crawler, WebUI backend/frontend) lives as a separate project under `modules/`, with shared config and contracts under `core/`. See [MODULAR_STRUCTURE.md](MODULAR_STRUCTURE.md) for the full target architecture.

**Current (legacy) layout:**

```
api/                 — Presentation (HTTP routes, CLI entrypoints)
application/         — Application (use cases, container/wiring)
domain/              — Domain (entities, services, ports, errors)
infrastructure/      — Infrastructure (Qdrant, Ollama, FS, crawl, logging)
config/              — Configuration (YAML + env)
utils/               — Pure helpers
tests/               — Pytest (domain, application, api, infrastructure)

modules/             — Separate projects: rag_service, crawler_service, webui_backend, webui_frontend  
CoreModules/         — Shared core apps/libs (e.g. LlmProxy, MdIngestionService / `md_ingestion_service`)
core/                — (Target) config, shared, contracts
```

## Data flow

- **HTTP**: Client → `api/http/rag_routes.py` (Flask) → `application/rag/use_cases.py` → `domain/services/*` + ports → `infrastructure/*` (Qdrant, Ollama).
- **CLI**: `api/cli/crawl_cli.py` (or `python WebUI/app.py crawl`) → delegates to WebUI/app.py crawl/index/rebuild.
- **RAG**: `query_for_retrieval` (domain) → embed (Ollama) → search (Qdrant) → rerank (Ollama) → `build_context_block` (domain) → chat (Ollama).

## Layers

- **api/**: Flask app (`create_app` in `api/http/rag_routes.py`), CLI wrappers (`api/cli/crawl_cli.py`). No direct infrastructure imports; uses application use cases.
- **application/**: RAG use cases (`build_rag_context`, `answer_question`, `search_rag`), crawl use cases (stubs), `application/container.py` for wiring default implementations.
- **domain/**: Entities (`RagChunk`, `RagContext`, `CrawlSource`, etc.), services (retrieval, rerank, chunking, metadata_inference, prompt_builder), ports (RagRepository, EmbeddingProvider, ChatLLMClient, CrawlRunner, MarkdownStore, RerankClient), errors (RetrievalError, EmbeddingError, etc.).
- **infrastructure/**: Ollama (embed, chat, rerank), Qdrant (RagRepository), FS (MarkdownStore), crawl (Playwright), logging (WebUI error logger).

## Running tests

From project root:

```bash
pip install -r requirements-dev.txt
pytest tests/
```

Configuration lives in **`pyproject.toml`** (`[tool.pytest.ini_options]`), including `pythonpath` entries for `modules/rag_service`, `CoreModules/MdIngestionService`, and `modules/crawler_service`.

Coverage report for domain and application:

```bash
pytest tests/ --cov=domain --cov=application --cov-report=term-missing
```

Domain and application tests use mocks; API tests use Flask test client with wired use cases.

## Python packaging (monorepo)

The repository root is an installable project **`chironai`** ([`pyproject.toml`](../pyproject.toml)):

- **Editable install**: `pip install -e ".[dev]"` installs top-level packages (`application`, `api`, `config`, `core`, `domain`, `infrastructure`, `utils`) and console scripts `tmrag` / `chironai`.
- **`modules/*`**: treated as separate subtrees (many already ship their own README / layout). They are on `sys.path` for tests via pytest `pythonpath`, not necessarily part of the `chironai` distribution—add them to setuptools `packages.find` only if you want a single wheel to include everything.
- **`CoreModules/OllamaInteractor`**: separate distribution `ollama-interactor`; the app invokes it via subprocess (see `infrastructure/ollama/cli_runner.py`).
- **`CoreModules/ServiceStarter`**: separate distribution `service-starter`; Docker Desktop + Ollama install (Windows), Qdrant/Open WebUI containers, and status (`pip install -e CoreModules/ServiceStarter`). WebUI delegates start/stop to it (see `api/http/webui_routes.py`).
- **`CoreModules/LlmProxy`**: separate distribution `llm-proxy`; OpenAI-compatible `/v1` HTTP surface (chat completions, models, apply-edit, external-docs ingest) as a Flask blueprint. The host app supplies a `LlmProxyWiring` built in [`api/http/llm_proxy_wiring.py`](../api/http/llm_proxy_wiring.py); see [`CoreModules/LlmProxy/README.md`](../CoreModules/LlmProxy/README.md).
- **`CoreModules/OpenClaw`**: optional distribution `openclaw`; separate-thread OpenAI-style **agent** HTTP on port 8082 (tool `rag_query` → existing RAG), optional MCP **info** HTTP on 8083, WebUI API under `/api/webui/openclaw`. Removing this tree + wiring hooks leaves the rest of ChironAI intact. See [`Claw.md`](../Claw.md) and [`CoreModules/OpenClaw/README.md`](../CoreModules/OpenClaw/README.md).
- **`CoreModules/WebInteraction`**: separate distribution `web-interaction`; free web snippet helpers (DuckDuckGo search, trigger heuristics) used when building the proxy system prompt. Wired from [`api/http/llm_proxy_wiring.py`](../api/http/llm_proxy_wiring.py); see [`CoreModules/WebInteraction/README.md`](../CoreModules/WebInteraction/README.md).
- **Import boundaries**: [import-linter](https://github.com/seddonym/import-linter) contract `domain_is_inner_layer` forbids `domain` → `application` | `api` | `infrastructure`. Run `lint-imports` after `pip install -r requirements-dev.txt`.

## Adding a new source or model

- **New embedding model**: configure in `config/models.yaml` (or env `RAG_EMBED_MODEL`); `OllamaEmbeddingProvider` uses it. No code change in domain/application.
- **New chat model**: configure in `config/models.yaml`; `OllamaChatClient` and `create_app` use it.
- **New crawl source**: add a source dict to WebUI/app.py `SOURCES`; crawl CLI and index flow use it. For a new crawler implementation, implement `CrawlRunner` in `infrastructure/crawl/` and wire it in the application layer.
- **New vector store**: implement `RagRepository` in `infrastructure/` and wire it in `application/container.py` instead of `QdrantRagRepository`.
