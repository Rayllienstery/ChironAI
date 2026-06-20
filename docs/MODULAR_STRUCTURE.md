# Modular Structure (Target Architecture)

This document describes the target repository layout and ownership model. The
main rule is simple: runtime code must not live at the repository root as an
unowned package. If the app needs it to start or behave correctly, it belongs to
`Core/`, `CoreModules/`, or the extension system.

## Top-Level Layout

```text
Core/                  # Application host and host-owned services
  api/                 # HTTP composition, route registration, legacy route tail
  application/         # Host application use cases
  domain/              # Host domain model and ports
  infrastructure/      # Host adapters, repositories, compatibility shims
  config/              # Host configuration authority
  core/                # Shared contracts/config package; import name remains `core`
  modules/             # Host-owned business services and apps
    crawler_service/
    extensions_backend/
    webui_backend/
    html_md/
    md_indexer/
    prompts_manager/
    tools/

CoreModules/           # Reusable modules/apps the host depends on
  CoreUI/              # React/Vite SPA
  DockerManager/
  ErrorManager/
  ExtensionsHost/
  ExtensionsSandbox/
  LlmInteractor/
  LlmProxy/
  LogsManager/
  MdIngestionService/
  RagService/
  Security/
  WebInteraction/

extensions/            # Installed/bundled extension payloads
docs/                  # Architecture and runbooks
scripts/               # Repo scripts and maintenance tooling
tests/                 # Test suite
WebUI/                 # Runtime/data folder, not frontend source
logs/                  # Runtime logs
tmp/                   # Temporary/dev-only material
```

During migration, some host-owned folders may still exist at the repository
root. Treat those as migration tails, not as permanent architecture. Phase 1
moved the main host packages into `Core/`; Phase 2 moved host-owned services
into `Core/modules/`; Phase 3 moved prompt templates under
`Core/modules/prompts_manager/` with runtime storage in `WebUI/prompts/`.

`scripts/root_layout_guard.py` is the automated root allowlist. Update that
guardrail and this document together when a root folder is intentionally added,
removed, or reclassified.

## Ownership Buckets

| Bucket | Responsibility |
|--------|----------------|
| **Core** | The application host: process composition, HTTP entrypoints, host layers, shared contracts/config, compatibility shims, and host-owned services. |
| **CoreModules** | Explicit reusable modules/apps with clear public responsibility, tests, and module boundaries. |
| **extensions** | Extension payloads managed through the extension backend and host/runtime contracts. |
| **project support** | Docs, tests, scripts, CI metadata, generated artifacts, and runtime data. |

`CoreModules/` is not a replacement name for every important folder. A package
is promoted to `CoreModules/` only when it is a standalone module with an
intentional public boundary. Host-specific code goes under `Core/`.

## Current Root Ownership

| Root folder | Owner | Classification |
|-------------|-------|----------------|
| `.agents/` | project support | agent metadata |
| `.cursor/` | project support | editor metadata |
| `.git/` | project support | VCS metadata |
| `.github/` | project support | CI metadata |
| `.import_linter_cache/` | project support | tool cache |
| `.kilo/` | project support | agent metadata |
| `.ruff_cache/` | project support | tool cache |
| `.tmp_openwebui_data/` | temporary | local runtime data |
| `.tmp_test_local/` | temporary | local test data |
| `.vscode/` | project support | editor metadata |
| `chironai.egg-info/` | project support | packaging metadata |
| `Core/` | Core | application host container |
| `CoreModules/` | CoreModules | reusable modules and applications |
| `docs/` | project support | architecture and runbooks |
| `extensions/` | extensions | extension payloads |
| `logs/` | runtime data | local logs and databases |
| `rag_tests/` | project support | RAG evaluation fixtures |
| `reports/` | project support | generated reports |
| `scripts/` | project support | repo tooling |
| `tests/` | project support | test suite |
| `tmp/` | temporary | scratch and cloned dependency worktrees |
| `WebUI/` | runtime data | runtime/data folder, not frontend source |

## Current-to-Target Path Map

| Current path | Target path | Notes |
|--------------|-------------|-------|
| `api/` | `Core/api/` | Keep import name `api` stable during the first migration pass. |
| `application/` | `Core/application/` | Host application layer. |
| `domain/` | `Core/domain/` | Inner host domain layer. Import boundary still applies. |
| `infrastructure/` | `Core/infrastructure/` | Host adapters and compatibility shims. |
| `config/` | `Core/config/` | Configuration authority and env/yaml loading. |
| `core/` | `Core/core/` | Shared contracts/config package; import name remains `core`. |
| `modules/*` | `Core/modules/*` | Host-owned services (webui_backend, extensions_backend, crawler_service, html_md, md_indexer, prompts_manager, tools, external_docs_rag). |

## Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| **Core/api** | HTTP composition and legacy route tail while migration continues. |
| **Core/core** | Shared contracts, DTOs, and config types used across host/modules. |
| **webui_backend** | WebUI backend entrypoints, dashboard/settings/log aggregation, and remaining legacy crawl/ingest helpers pending extraction. |
| **extensions_backend** | Extension registry, repository metadata, install/update/remove, local install state, blocklist, runtime status, and marketplace governance. |
| **crawler_service** | Crawl web/docs sources and feed ingestion/indexing through contracts. |
| **RagService** | Full RAG pipeline: retrieval, rerank, prompt, and answer generation contracts/runtime. |
| **MdIngestionService** | Markdown/document ingestion, filtering, chunking, and prepare-for-indexing flow. |
| **CoreUI** | React SPA. Talks to the backend only over HTTP. |
| **ExtensionsHost** | Host/runtime contracts and capability bridge (`extensions_host`). Wires `extensions_backend` with `llm_interactor`; does not own registry polling or marketplace policy. |
| **ExtensionsSandbox** | Out-of-process extension worker isolation. |

## Dependency Rules

- Root runtime packages are forbidden unless explicitly allowlisted as migration
  tails.
- Physical moves should preserve public import names in the first pass. Add
  `Core/` and relevant `Core/modules/*` paths to tooling instead of renaming
  imports everywhere at once.
- `domain` must not import `application`, `api`, or `infrastructure`.
- Modules must not import each other's concrete implementations. Communicate via
  `Core/core/contracts/*` (import name `core.contracts` while stable), stable
  Python protocols, or HTTP contracts.
- `CoreUI` source stays under `CoreModules/CoreUI`. Non-extension backend
  modules do not own browser-rendered UI.
- Extension discovery, registry polling, install/update/remove, blocklist, and
  extension status polling belong to `extensions_backend`. CoreModules expose
  only host/runtime contracts and consume extension state through contracts.

## Data Flow

```text
CoreUI
  -> Web UI HTTP API
  -> webui_backend / host API composition
  -> contracts / HTTP
  -> RagService, MdIngestionService, crawler_service, extensions_backend
```

Extension flow:

```text
CoreUI
  -> Web UI HTTP API
  -> webui_backend
  -> extensions_backend
  -> ExtensionsHost / ExtensionsSandbox
  -> extension workers
```

Provider flow:

```text
LlmProxy
  -> provider runtime contract
  -> ExtensionsHost
```

`LlmProxy` must not know where extensions are installed or how registry state is
loaded.

## Migration Principles

1. Clean the root by ownership, not by blindly moving folders into
   `CoreModules/`.
2. Move physical paths separately from public import renames.
3. Reduce legacy tails by bounded context: prompts, WebUI routes, crawler/indexer,
   settings, service control, provider runtime, and extension ownership.
4. Update `AI_RULES.md`, `docs/legacy_map.md`, package/tool paths, and tests in
   the same change that changes ownership.
5. Add a root-layout guardrail before or during the first physical move so new
   freelance runtime packages cannot appear unnoticed.

## Tests

- Legacy tests remain under `tests/` and should keep importing stable package
  names while physical paths move.
- Module-specific tests should live with the repo test suite or the module once
  the module is independently packaged.
- After moving host packages, run import smoke checks for `api`, `application`,
  `domain`, `infrastructure`, `config`, `core`, `webui_backend`, and
  `extensions_backend`.
- After changing CoreUI source, run the CoreUI production build or an equivalent
  JSX/parser check.
