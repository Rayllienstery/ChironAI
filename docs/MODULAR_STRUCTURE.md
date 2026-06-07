# Modular Structure (Target Architecture)

This document describes the target layout of the repository: **modules** as separate projects in their own folders, and **core** for shared config and contracts. Communication between modules is via **interfaces** (Python protocols / HTTP contracts).

## Top-Level Layout

```
modules/           — Business projects (each with own README, deps, entrypoints)
  crawler_service/
  extensions_backend/ - Extension registry/discovery/install/status module; owns marketplace state
  webui_backend/
  CoreUI/           — React/Vite SPA under CoreModules/CoreUI (current Web UI frontend)
  md_indexer/       — Config-driven markdown cleanup pipelines (under modules/md_indexer)
CoreModules/       — Core libraries and apps (LlmProxy, RagService, MdIngestionService, …)
  RagService/       — pip `chironai-rag-service`: `rag_service` pipeline + `chironai_rag` contracts
  ExtensionsHost/ - Target extension host/runtime contracts and capability bridge
  ExtensionsSandbox/ - Out-of-process extension worker isolation
  MdIngestionService/
    md_ingestion_service/   — Python package (ingest, prepare_markdown_for_indexing, CLI)
core/               — Shared infrastructure (named "core" to avoid shadowing Python stdlib "platform")
  config/           — Typed config models, YAML/env loader
  shared/           — Common types, errors, utilities
  contracts/        — Inter-module API contracts (HTTP, DTOs)
docs/               — Architecture and runbooks
docker-compose.yml  — Services for each module (when migrated)
```

## Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| **rag_service** | Full RAG pipeline: retrieval → rerank → prompt → LLM answer. HTTP API + optional CLI. |
| **md_ingestion_service** | Lives under **CoreModules/MdIngestionService**: pre-RAG prepare (`indexing.yaml` + md_indexer), filtering, chunking. Feeds RAG via contract. |
| **crawler_service** | Crawl web/docs sources; push results to md_ingestion_service via contract. |
| **extensions_backend** | Extension registry, repository metadata, install/update/remove, local install state, blocklist, runtime status, and marketplace governance. Calls extension host/runtime only through contracts. |
| **webui_backend** | Canonical WebUI backend package under `modules/webui_backend`: entrypoints, dashboard/settings/logs target layers, and remaining legacy crawl/ingest helpers pending further extraction. |
| **CoreUI** (under `CoreModules/CoreUI`) | React SPA; talks to the WebUI HTTP API through the canonical `webui_backend` entrypoints. |
| **ExtensionsHost** (under `CoreModules/ExtensionsHost`, target) | Stable host/runtime contracts, provider bridge, host capabilities, and sandbox protocol surface. Does not own registry polling, repository metadata fetching, install state, or marketplace policy. |
| **tools** | Optional scripts/CLI that call multiple modules. |

## Dependency Rules

- **Modules** must not import each other's concrete implementations (e.g. no `from rag_service.infrastructure import ...` from webui_backend).
- **Communication**: via `core/contracts/*` (HTTP schemas, DTOs) and HTTP/gRPC. In-process use is via interfaces (Protocol/ABC) implemented in each module and consumed by others through contracts.
- **Core** is the only shared dependency; keep `core/shared` minimal.
- **Extensions boundary:** extension discovery, registry polling, install/update/remove, blocklist, and extension status polling belong to `extensions_backend`, not core modules. Core modules expose only host/runtime contracts and consume extension state through contracts.

## Per-Module Layout (Python services)

Each service under `modules/<name>/` follows the same pattern:

- `README.md` — Purpose, how to init, env vars, API summary.
- `pyproject.toml` or `requirements.txt` — Dependencies.
- `<name>/` (Python package):
  - `domain/` — entities, services, ports, errors
  - `application/` — use cases, DTOs
  - `infrastructure/` — adapters (DB, HTTP, Ollama, Qdrant, etc.)
  - `api/` — HTTP routes, CLI
- `tests/` — Unit and integration tests.

## Data Flow

- **Frontend** → HTTP → **webui_backend** → HTTP (contracts) → **rag_service**, **md_ingestion_service**, **crawler_service**.
- **crawler_service** → HTTP (contract) → **md_ingestion_service**.
- **md_ingestion_service** → HTTP (contract) → **rag_service** (indexing).

- Extension flow: **Frontend** -> HTTP -> **webui_backend** -> HTTP/contracts -> **extensions_backend** -> **ExtensionsHost** -> sandboxed extension workers.
- Provider flow: **LlmProxy** -> provider runtime contract -> **ExtensionsHost**. LlmProxy must not know where extensions are installed or how the registry works.

See the plan diagram (flowchart) for a visual summary.

## Tests

- Legacy tests remain under `tests/` (domain, application, api, infrastructure) and target the root packages.
- Module-specific tests live under `tests/rag_service/`, `tests/md_ingestion_service/`, `tests/crawler_service/` and import from the corresponding module packages. Run from repo root: `pip install -r requirements-dev.txt` then `pytest tests/` (pytest.ini adds module roots to pythonpath).

## Migration from Current Layout

The existing codebase (`api/`, `application/`, `domain/`, `infrastructure/`, `config/`) remains; the Web UI frontend lives under **`CoreModules/CoreUI`**. The canonical `webui_backend` package now lives under `modules/webui_backend`; the remaining WebUI route-composition tail lives under `api/http/webui_routes.py` and related `webui_*_routes.py` files.

Extension migration: current direct wiring through `api/http/*`, `llm_proxy_wiring.py`, `CoreModules/LlmInteractor`, and local `extensions/bundled` scanning is migration tail. Target state moves registry/discovery/install/status ownership to `extensions_backend`; core modules keep only extension host/runtime contracts and sandbox/capability surfaces.
