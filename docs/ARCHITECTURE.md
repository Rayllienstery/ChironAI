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

modules/             — (Target) Separate projects: rag_service, md_ingestion_service, crawler_service, webui_backend, webui_frontend
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

Coverage report for domain and application:

```bash
pytest tests/ --cov=domain --cov=application --cov-report=term-missing
```

Domain and application tests use mocks; API tests use Flask test client with wired use cases.

## Adding a new source or model

- **New embedding model**: configure in `config/models.yaml` (or env `RAG_EMBED_MODEL`); `OllamaEmbeddingProvider` uses it. No code change in domain/application.
- **New chat model**: configure in `config/models.yaml`; `OllamaChatClient` and `create_app` use it.
- **New crawl source**: add a source dict to WebUI/app.py `SOURCES`; crawl CLI and index flow use it. For a new crawler implementation, implement `CrawlRunner` in `infrastructure/crawl/` and wire it in the application layer.
- **New vector store**: implement `RagRepository` in `infrastructure/` and wire it in `application/container.py` instead of `QdrantRagRepository`.
